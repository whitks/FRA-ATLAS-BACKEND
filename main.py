from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_restful import Api, Resource
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required
)
from datetime import datetime, timedelta
from flask_cors import CORS
from pathlib import Path
from flask_socketio import SocketIO, emit
import threading
from groq import Groq
from chatBot import Human
# chatBot.py
import os
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
# Load environment variables from .env
load_dotenv()
import utm
# Get the API key
APIKEY = os.getenv("APIKEY")
if not APIKEY:
    APIKEY= "123"
client = Groq(api_key=APIKEY)
# --- DSS imports ---
from dss import (
    fetch_lulc_data,
    get_claims_for_district,
    check_scheme_eligibility,
    summarize_scheme_eligibility,
    get_aoi_lulc_stats
)
from dss import get_lgeom_properties,parse_lgeom_properties

#BRRRRRRRRRRRRR________________TOKENS TOKENS I REPEAT THE TOKENS ARE HERE

district_lulc_stats_token="0670314ca018c20e53939ce6fe7b53eebeb98cff"


aoi_stats_lulc_token="1a225e779c434461318e9026784947f26d38bfaa"


# --- Flask App Config ---
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- Flask App Config ---
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "instance" / "fra.db"
UPLOAD_FOLDER = BASE_DIR / "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = "super-secret"  # ⚠️ Change in production
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)

db = SQLAlchemy(app)
api = Api(app)
jwt = JWTManager(app)

# --- Models ---
class DLC(db.Model):
    _tablename_ = "dlc"
    id = db.Column(db.Integer, primary_key=True)
    f_name = db.Column(db.String(100))
    l_name = db.Column(db.String(100))
    email = db.Column(db.String(150), unique=True)
    phone = db.Column(db.String(20))
    password = db.Column(db.String(255))
    sdlcs = db.relationship("SDLC", backref="dlc", cascade="all, delete-orphan")

class SDLC(db.Model):
    _tablename_ = "sdlc"
    id = db.Column(db.Integer, primary_key=True)
    f_name = db.Column(db.String(100))
    l_name = db.Column(db.String(100))
    email = db.Column(db.String(150), unique=True)
    phone = db.Column(db.String(20))
    password = db.Column(db.String(255))
    dlc_id = db.Column(db.Integer, db.ForeignKey("dlc.id"), nullable=False)
    gram_sabhas = db.relationship("GRAM_SABHA", backref="sdlc", cascade="all, delete-orphan")

class GRAM_SABHA(db.Model):
    _tablename_ = "gram_sabha"
    id = db.Column(db.Integer, primary_key=True)
    f_name = db.Column(db.String(100))
    l_name = db.Column(db.String(100))
    email = db.Column(db.String(150), unique=True)
    phone = db.Column(db.String(20))
    password = db.Column(db.String(255))
    sdlc_id = db.Column(db.Integer, db.ForeignKey("sdlc.id"), nullable=False)

class FRAClaim(db.Model):
    _tablename_ = "fra_claims"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    source_file = db.Column(db.String(255))
    holder_id = db.Column(db.Integer)
    address = db.Column(db.String(255))
    village_details = db.Column(db.String(255), nullable=True)
    khasara_no = db.Column(db.String(255))
    land_area = db.Column(db.String(255))
    purpose = db.Column(db.String(255))
    caste_status = db.Column(db.String(255))
    forest_block_name = db.Column(db.String(255))
    compartment_no = db.Column(db.String(255))
    latitude = db.Column(db.String(255))
    longitude = db.Column(db.String(255))
    level = db.Column(db.String(255))
    remark = db.Column(db.String(255))
    approved = db.Column(db.Boolean(), default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ClaimSource(db.Model):
    __tablename__ = "claim_sources"

    id = db.Column(db.Integer, primary_key=True)
    source_file = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)



def get_user_model(role):
    return {"dlc": DLC, "sdlc": SDLC, "gram_sabha": GRAM_SABHA}.get(role)

# --- Auth Resources ---
class Register(Resource):
    def post(self, role):
        data = request.get_json()
        model = get_user_model(role)
        if not model:
            return {"msg": "Invalid role"}, 400
        if model.query.filter_by(email=data["email"]).first():
            return {"msg": "User already exists"}, 400
        user = model(
            f_name=data.get("f_name"),
            l_name=data.get("l_name"),
            email=data["email"],
            phone=data.get("phone"),
            password=data["password"]
        )
        db.session.add(user)
        db.session.commit()
        return {"msg": "User registered successfully"}, 201

class Login(Resource):
    def post(self, role):
        data = request.get_json()
        model = get_user_model(role)
        if not model:
            return {"msg": "Invalid role"}, 400
        user = model.query.filter_by(email=data["email"]).first()
        if not user or user.password != data["password"]:
            return {"msg": "Invalid credentials"}, 401
        token = create_access_token(identity=user.email, additional_claims={"role": role})
        return {"access_token": token}, 200

from sqlalchemy import func

def next_claim_id():
    """Find the next available claim_id shared across FRAClaim and ClaimSource."""
    fra_max = db.session.query(func.max(FRAClaim.id)).scalar() or 0
    src_max = db.session.query(func.max(ClaimSource.id)).scalar() or 0
    return max(fra_max, src_max) + 1


class AddClaim(Resource):
    def post(self):
        data = request.get_json()

        # Generate next shared ID
        new_id = next_claim_id()

        if data.get("source_file"):
            claim = ClaimSource(id=new_id, source_file=data.get("source_file"))
            db.session.add(claim)
            db.session.commit()
            return {
                "msg": "Claim source added successfully",
                "id": claim.id
            }, 201


        claim = FRAClaim(
            id=new_id,
            source_file=data.get("source_file"),
            holder_id=data.get("holder_id"),
            address=data.get("address"),
            village_details=data.get("village_details"),
            khasara_no=data.get("khasara_no"),
            land_area=data.get("land_area"),
            purpose=data.get("purpose"),
            caste_status=data.get("caste_status"),
            forest_block_name=data.get("forest_block_name"),
            compartment_no=data.get("compartment_no"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
        )

        db.session.add(claim)
        db.session.commit()

        return {
            "msg": "FRA Claim added successfully",
            "claim": {
                "id": claim.id,
                "source_file": claim.source_file,
                "holder_id": claim.holder_id,
                "address": claim.address,
                "village_details": claim.village_details,
                "khasara_no": claim.khasara_no,
                "land_area": claim.land_area,
                "purpose": claim.purpose,
                "caste_status": claim.caste_status,
                "forest_block_name": claim.forest_block_name,
                "compartment_no": claim.compartment_no,
                "latitude": claim.latitude,
                "longitude": claim.longitude,
                "approved": claim.approved,
                "created_at": claim.created_at.isoformat() ,
                "updated_at": claim.updated_at.isoformat() 
            }
        }, 201
class GetClaims(Resource):
    def get(self):
        claims = FRAClaim.query.all()
        result = []
        for c in claims:
            result.append({
                "id": c.id,
                "source_file": c.source_file,
                "holder_id": c.holder_id,
                "address": c.address,
                "village_details": c.village_details,
                "khasara_no": c.khasara_no,
                "land_area": c.land_area,
                "purpose": c.purpose,
                "caste_status": c.caste_status,
                "forest_block_name": c.forest_block_name,
                "compartment_no": c.compartment_no,
                "latitude": c.latitude,
                "longitude": c.longitude,
                "level": c.level,
                "remark": c.remark,
                "approved": c.approved,
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat()
            })
        return jsonify(result)

# --- DSS Endpoints ---
class LULC(Resource):
    def get(self, distcode="0831"):
        DISTRICT_TOKEN = district_lulc_stats_token  # new token
        year = request.args.get("year", "1112")
        data = fetch_lulc_data(distcode, DISTRICT_TOKEN, year)
        return jsonify(data)

class DistrictClaims(Resource):
    def get(self, district):
        db_path = Path("instance/fra.db")
        claims = get_claims_for_district(db_path, district)
        return jsonify(claims)

class ClaimEligibility(Resource):
    def get(self, claim_id):
        db_path = Path("instance/fra.db")
        district = request.args.get("district", "बारां")
        DISTRICT_TOKEN = district_lulc_stats_token  # new token
        distcode = request.args.get("distcode", "0831")
        lulc_data = fetch_lulc_data(distcode, DISTRICT_TOKEN)
        claims = get_claims_for_district(db_path, district)
        claim = next((c for c in claims if c["id"] == int(claim_id)), None)
        if not claim:
            return {"msg": "Claim not found"}, 404
        eligibility = check_scheme_eligibility(claim, lulc_data)
        return jsonify(eligibility)

class DistrictEligibilitySummary(Resource):
    def get(self, district):
        db_path = Path("instance/fra.db")
        DISTRICT_TOKEN = district_lulc_stats_token  # new token
        distcode = request.args.get("distcode", "0831")
        lulc_data = fetch_lulc_data(distcode, DISTRICT_TOKEN)
        summary = summarize_scheme_eligibility(db_path, district, lulc_data)
        return jsonify(summary)

class AOILULC(Resource):
    def post(self):
        data = request.get_json()
        geom = data.get("geom")
        AOI_TOKEN = aoi_stats_lulc_token  # new AOI token
        result = get_aoi_lulc_stats(geom, AOI_TOKEN)
        return jsonify(result)

users = {}
@socketio.on("connect")
def handle_connect():
    print(f"✅ Client connected: {request.sid}")
    users[request.sid] = Human(request.sid)
    emit("connected", {"message": "Connected to AI Chatbot!"})

@socketio.on("disconnect")
def handle_disconnect():
    print(f"❌ Client disconnected: {request.sid}")
    users.pop(request.sid, None)

@socketio.on("message")
def handle_message(data):
    """Handles incoming user messages and streams AI responses"""
    sid = request.sid  # ✅ Capture it while still in context
    print(f"📩 User ({sid}): {data}")

    person = users.get(sid)
    if not person:
        person = Human(sid)
        users[sid] = person

    person.add_message("user", data)

    def generate_response(sid):
        try:
            completion = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=person.get_messages(),
            )
            # ✅ Use captured sid
            socketio.emit(
                "response",
                {"text": completion.choices[0].message.content},
                to=sid
            )
        except Exception as e:
            print(f"⚠️ Error generating response for {sid}: {e}")

    # ✅ Pass sid to thread
    threading.Thread(target=generate_response, args=(sid,)).start()
    from werkzeug.utils import secure_filename

class UploadDocument(Resource):
    def post(self):
        """
        Upload a document and save it under /uploads/<claim_id>/<filename>.
        It uses next_claim_id() to generate the claim ID.
        """
        if "file" not in request.files:
            return {"msg": "No file part in request"}, 400
        
        file = request.files["file"]
        if file.filename == "":
            return {"msg": "No selected file"}, 400
        
        # Generate claim ID using existing helper
        claim_id = next_claim_id()
        
        # Sanitize and save file
        filename = secure_filename(file.filename)
        claim_folder = app.config["UPLOAD_FOLDER"] / str(claim_id)
        os.makedirs(claim_folder, exist_ok=True)
        
        file_path = claim_folder / filename
        file.save(file_path)
        
        # Optionally log it to the database (ClaimSource)
        claim_source = ClaimSource(id=claim_id, source_file=str(file_path))
        db.session.add(claim_source)
        db.session.commit()
        
        return {
            "msg": "File uploaded successfully",
            "claim_id": claim_id,
            "file_path": f"/uploads/{claim_id}/{filename}"
        }, 201
import os

class GetUploadedFiles(Resource):
    def get(self, claim_id):
        """
        Returns all uploaded files for a given claim ID.
        Looks inside /uploads/<claim_id>/ and lists files.
        """
        claim_folder = app.config["UPLOAD_FOLDER"] / str(claim_id)
        
        # Check if folder exists
        if not claim_folder.exists():
            return {"msg": f"No uploads found for claim ID {claim_id}"}, 404
        
        # List files in folder
        files = [
            f for f in os.listdir(claim_folder)
            if os.path.isfile(os.path.join(claim_folder, f))
        ]

        file_urls = [
            f"/uploads/{claim_id}/{f}" for f in files
        ]

        return {
            "claim_id": claim_id,
            "file_count": len(files),
            "files": file_urls,
        }, 200

# --- Routes ---
api.add_resource(Register, "/register/<string:role>")
api.add_resource(Login, "/login/<string:role>")
api.add_resource(AddClaim, "/claims")
api.add_resource(GetClaims, "/claims/all")
api.add_resource(LULC, "/lulc/<string:distcode>")
api.add_resource(DistrictClaims, "/claims/district/<string:district>")
api.add_resource(ClaimEligibility, "/eligibility/<int:claim_id>")
api.add_resource(DistrictEligibilitySummary, "/eligibility/summary/<string:district>")
api.add_resource(AOILULC, "/lulc/aoi")
api.add_resource(UploadDocument, "/upload")
api.add_resource(GetUploadedFiles, "/uploads/<int:claim_id>")


class LGeom(Resource):
    """
    Lookup RJ_LGEOM groundwater properties for a coordinate.

    GET /lgeom?x=<float>&y=<float>
    POST /lgeom  { "x": <float>, "y": <float> }

    Returns JSON from `get_lgeom_properties` or an error message.
    """

    # Default buffer size (fixed for prototype)
    DEFAULT_BUFFER_SIZE = 500

    def _latlon_to_xy_epsg(self, lat, lon):
        """
        Convert latitude and longitude to UTM coordinates and determine the correct EPSG code.
        Northern hemisphere: EPSG:326XX
        Southern hemisphere: EPSG:327XX
        """

        # Convert lat/lon to UTM
        easting, northing, zone_number, zone_letter = utm.from_latlon(lat, lon)

        # Determine correct EPSG code
        if zone_letter >= 'N':
            epsg_code = f"EPSG:{32600 + zone_number}"  # Northern hemisphere
        else:
            epsg_code = f"EPSG:{32700 + zone_number}"  # Southern hemisphere

        return easting, northing, epsg_code

    def _parse_params(self):
        """
        Parse input parameters from GET or POST and return:
        x, y, srs, buffer_size
        """
        if request.method == "GET":
            lat_str = request.args.get("x")
            lon_str = request.args.get("y")
        else:
            data = request.get_json(silent=True) or {}
            lat_str = data.get("y")
            lon_str = data.get("x")
        print(lat_str,lon_str)
        # Validate lat/lon
        if lat_str is None or lon_str is None:
            raise ValueError("Missing parameters 'x' or 'y'")

        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except Exception:
            raise ValueError("Invalid numeric values for 'x' or 'y'")

        # Convert to UTM and determine EPSG automatically
        x, y, srs = self._latlon_to_xy_epsg(lat, lon)

        # Use fixed buffer size
        buffer_size = self.DEFAULT_BUFFER_SIZE

        return x, y, srs, buffer_size

    def get(self):
        try:
            x, y, srs, buffer_size = self._parse_params()
            print(f"Parsed GET params: x={x}, y={y}, srs={srs}, buffer_size={buffer_size}")
        except ValueError as e:
            return {"error": str(e)}, 400

        try:
            result = get_lgeom_properties(x, y, buffer_size=buffer_size)
            return jsonify(result)
        except Exception as e:
            return {"error": str(e)}, 500

    def post(self):
        try:
            x, y, srs, buffer_size = self._parse_params()
            print(f"Parsed POST params: x={x}, y={y}, srs={srs}, buffer_size={buffer_size}")
        except ValueError as e:
            return {"error": str(e)}, 400

        try:
            result = get_lgeom_properties(x, y,srs = srs, buffer_size=buffer_size)
            final = parse_lgeom_properties(result)
            return jsonify(final)
        except Exception as e:
            return {"error": str(e)}, 500
        


api.add_resource(LGeom, "/lgeom")
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    socketio.run(app, host="0.0.0.0", port=3000, debug=True, allow_unsafe_werkzeug=True)