import streamlit as st
from PIL import Image
import datetime
import gspread
import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ==========================
# 📌 Title
# ==========================
st.title("📦 โปรแกรมการนับพาเลทด้วย AI สำหรับโรงงาน TWN")

# ใช้ session_state เพื่อจำสถานะของหน้า
if "page" not in st.session_state:
    st.session_state.page = "page1"

# ==========================
# 📄 PAGE 1: ระบุเอกสารและถ่ายรูป
# ==========================
if st.session_state.page == "page1":
    st.header("📄 ขั้นตอนที่ 1: ระบุเอกสารใบคุมพาเลท")

    ocr_text = st.text_input("โปรดระบุเลขที่ใบคุมพาเลท (ไม่ต้องใส่ PT) เช่น 1234")
    doc_image = st.camera_input("ถ่ายรูปเอกสารใบคุมพาเลท")

    if st.button("➡️ ถัดไป (ไปหน้าถ่ายพาเลท)"):
        if not ocr_text:
            st.warning("⚠️ กรุณากรอกเลขที่ใบคุมพาเลทก่อน")
        elif not doc_image:
            st.warning("⚠️ กรุณาถ่ายรูปเอกสารก่อน")
        else:
            st.session_state.ocr_text = ocr_text
            st.session_state.doc_image = doc_image
            st.session_state.page = "page2"
            st.experimental_rerun()

# ==========================
# 📦 PAGE 2: ถ่ายพาเลท + ตรวจจับ + บันทึก
# ==========================
elif st.session_state.page == "page2":
    st.header("📦 ขั้นตอนที่ 2: ตรวจนับพาเลท")

    pallet_image_file = st.camera_input("ถ่ายรูปพาเลท 1 ด้าน")

    detected_count = 0
    if pallet_image_file:
        temp_image_path = "pallet_temp.jpg"
        image = Image.open(pallet_image_file)
        image.save(temp_image_path)

        try:
            response = requests.post(
                "https://detect.roboflow.com/pallet-detection-measurement/1?api_key=WtsFf6wpMhlX16yRNb6e",
                files={"file": open(temp_image_path, "rb")}
            )
            result = response.json()
            predictions = result.get("predictions", [])
            detected_count = len(predictions)
            st.success(f"🎯 ตรวจจับได้ {detected_count} พาเลท")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดระหว่างตรวจจับ: {e}")

    pallet_count = st.number_input("โปรดยืนยันจำนวนพาเลท", value=detected_count, step=1)

    if st.button("⬅️ กลับไปหน้าเอกสาร"):
        st.session_state.page = "page1"
        st.experimental_rerun()

    if st.button("✅ ยืนยันและบันทึกข้อมูล"):
        try:
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_info(st.secrets["gcp"], scopes=scopes)
            gc = gspread.authorize(creds)
            sheet = gc.open_by_key("1GR4AH-WFQCA9YGma6g3t0APK8xfMW8DZZkBQAqHWg68").sheet1
            drive_service = build("drive", "v3", credentials=creds)

            folder_name = "Pallet"
            query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
            results = drive_service.files().list(q=query, spaces='drive', fields='files(id)').execute()
            if results.get("files"):
                folder_id = results["files"][0]["id"]
            else:
                folder = drive_service.files().create(
                    body={'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'},
                    fields='id'
                ).execute()
                folder_id = folder['id']

            def upload_image(file_obj, prefix):
                if not file_obj:
                    return "No Image"
                temp_path = f"{prefix}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
                Image.open(file_obj).save(temp_path)
                media = MediaFileUpload(temp_path, mimetype='image/jpeg')
                uploaded = drive_service.files().create(
                    body={'name': temp_path, 'parents': [folder_id]},
                    media_body=media,
                    fields='id'
                ).execute()
                return f"https://drive.google.com/file/d/{uploaded['id']}/view?usp=sharing"

            doc_link = upload_image(st.session_state.doc_image, "Document")
            pallet_link = upload_image(pallet_image_file, "Pallet")

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = [timestamp, st.session_state.ocr_text, detected_count, pallet_count, doc_link, pallet_link]
            sheet.append_row(row)

            st.success("✅ บันทึกข้อมูลเรียบร้อยแล้ว!")


        except Exception as e:
            st.error(f"❌ ไม่สามารถบันทึกข้อมูลได้: {e}")


