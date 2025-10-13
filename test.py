import requests
import os

# URL of your running Flask backend
BASE_URL = "http://127.0.0.1:3000"
BULK_UPLOAD_ENDPOINT = f"{BASE_URL}/bulkupload"

# Path to your ZIP file (must exist)
ZIP_FILE_PATH = "falana.zip"  # <-- change this if your zip file is named differently

def test_bulk_upload():
    if not os.path.exists(ZIP_FILE_PATH):
        print(f"❌ ZIP file not found at: {ZIP_FILE_PATH}")
        return

    print(f"📦 Uploading ZIP file: {ZIP_FILE_PATH}")
    try:
        with open(ZIP_FILE_PATH, "rb") as zip_file:
            files = {"file": (os.path.basename(ZIP_FILE_PATH), zip_file, "application/zip")}
            response = requests.post(BULK_UPLOAD_ENDPOINT, files=files)

        print(f"✅ Status Code: {response.status_code}")
        try:
            data = response.json()
            print("📋 Response JSON:")
            for key, value in data.items():
                print(f"{key}: {value}")
        except Exception:
            print("⚠️ Non-JSON response:", response.text)

    except Exception as e:
        print("❌ Error during upload:", e)


if __name__ == "__main__":
    test_bulk_upload()
