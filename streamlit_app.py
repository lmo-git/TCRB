import streamlit as st
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np
import uuid
import datetime
import gspread
import requests
import re
import easyocr
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# ======================================================
# STYLE: Make Camera Bigger for Android
# ======================================================
st.markdown(
    """
    <style>
    div[data-testid="stCameraInput"] video {
        width: 100% !important;
        height: 100vh !important;
        object-fit: cover !important;
        transform: scale(1.05);
        transform-origin: center;
    }
    div[data-testid="stCameraInput"] button {
        transform: scale(1.3);
        padding: 12px 20px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# OCR Reader
reader = easyocr.Reader(['en', 'th'], gpu=False)

# ======================================================
# TITLE
# ======================================================
st.title("📦 AI นับพาเลท TCRB")

# ======================================================
# SESSION INIT
# ======================================================
if "page" not in st.session_state:
    st.session_state.page = "page1"

if "pt_list" not in st.session_state:
    st.session_state.pt_list = []


# ======================================================
# Extract PT number from text
# ======================================================
def extract_pt_number(text):
    match = re.search(r"PT(\d+)", text)
    if match:
        return match.group(1)
    return None


def add_pt(pt_raw):
    pt = extract_pt_number(pt_raw)
    if pt:
        if pt not in st.session_state.pt_list:
            if len(st.session_state.pt_list) < 4:
                st.session_state.pt_list.append(pt)
                st.success(f"เพิ่ม PT: PT{pt}")
            else:
                st.warning("เก็บได้สูงสุด 4 PT เท่านั้น")
        else:
            st.info("เลข PT นี้มีอยู่แล้ว")
    else:
        st.error("❌ ไม่พบเลขหลัง PT")


# ======================================================
# PAGE 1 — SCAN PT (OCR)
# ======================================================
if st.session_state.page == "page1":

    st.header("📄 ขั้นตอนที่ 1: อ่านเลข PT จากภาพ (สูงสุด 4 ค่า)")

    pt_image = st.camera_input("📸 ถ่ายภาพที่มีเลข PT")

    if pt_image:
        # เปิดรูป
        img = Image.open(pt_image).convert("RGB")

        # Preprocessing
        img = img.filter(ImageFilter.SHARPEN)
        img = ImageEnhance.Sharpness(img).enhance(3.0)
        img = ImageEnhance.Contrast(img).enhance(1.8)

        # Resize upscale
        w, h = img.size
        img = img.resize((w * 2, h * 2))

        # OCR
        result = reader.readtext(np.array(img), detail=0)
        text = " ".join(result)

        st.write("📝 ข้อความ OCR:", text)

        # Extract PT
        add_pt(text)

    # แสดง PT ที่เก็บได้
    st.subheader("📌 รายการ PT:")
    if st.session_state.pt_list:
        for i, pt in enumerate(st.session_state.pt_list, 1):
            st.write(f"{i}. PT{pt}")
    else:
        st.info("ยังไม่มี PT ที่อ่านได้")

    # ปุ่มล้าง
    if st.button("🗑 ล้างทั้งหมด"):
        st.session_state.pt_list = []
        st.rerun()

    # ไปหน้า 2
    if st.button("➡️ ถัดไป (ไปถ่ายพาเลท)"):
        if len(st.session_state.pt_list) == 0:
            st.warning("โปรดสแกน PT อย่างน้อย 1 ค่า")
        else:
            st.session_state.page = "page2"
            st.rerun()


# ======================================================
# PAGE 2 — PALLET DETECTION
# ======================================================
elif st.session_state.page == "page2":

    st.header("📦 ขั้นตอนที่ 2: ตรวจนับพาเลท")

    st.subheader("📌 PT ที่สแกนแล้ว:")
    for pt in st.session_state.pt_list:
        st.code(f"PT{pt}")

    pallet_image = st.camera_input("📸 ถ่ายรูปพาเลท")

    detected_count = 0
    bytes_data = None

    if pallet_image:
        bytes_data = pallet_image.getvalue()
        temp_file = "pallet_temp.jpg"

        with open(temp_file, "wb") as f:
            f.write(bytes_data)

        try:
            response = requests.post(
                "https://detect.roboflow.com/pallet-detection-measurement/1?api_key=WtsFf6wpMhlX16yRNb6e",
                files={"file": open(temp_file, "rb")},
                timeout=20
            )
            predictions = response.json().get("predictions", [])
            detected_count = len(predictions)

            st.success(f"🎯 AI ตรวจจับพาเลทได้ {detected_count} กอง")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาด: {e}")

    pallet_count = st.number_input("จำนวนพาเลทที่ยืนยัน:", value=detected_count, step=1)

    # ปุ่มย้อนกลับ
    if st.button("⬅️ กลับไปอ่าน PT"):
        st.session_state.page = "page1"
        st.rerun()


    # ======================================================
    # SAVE DATA
    # ======================================================
    if st.button("✅ ยืนยันและบันทึกข้อมูล"):
        if bytes_data is None:
            st.warning("กรุณาถ่ายรูปพาเลทก่อน")
        else:
            try:
                # Google Auth
                scopes = [
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
                creds = Credentials.from_service_account_info(st.secrets["gcp"], scopes=scopes)
                gc = gspread.authorize(creds)
                sheet = gc.open_by_key("1GR4AH-WFQCA9YGma6g3t0APK8xfMW8DZZkBQAqHWg68").sheet1
                drive_service = build("drive", "v3", credentials=creds)

                # Google Drive folder
                folder_name = "Pallet"
                result = drive_service.files().list(
                    q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'",
                    fields="files(id)"
                ).execute()

                if result.get("files"):
                    folder_id = result["files"][0]["id"]
                else:
                    folder_id = drive_service.files().create(
                        body={"name": folder_name, "mimeType": "application/vnd.google-apps.folder"},
                        fields="id"
                    ).execute()["id"]

                # Upload function
                def upload_to_drive(file_bytes, prefix):
                    file_name = f"{prefix}_{uuid.uuid4().hex}.jpg"
                    with open(file_name, "wb") as f:
                        f.write(file_bytes)

                    media = MediaFileUpload(file_name, mimetype="image/jpeg")
                    uploaded = drive_service.files().create(
                        body={"name": file_name, "parents": [folder_id]},
                        media_body=media,
                        fields="id"
                    ).execute()

                    return f"https://drive.google.com/file/d/{uploaded['id']}/view"

                pallet_link = upload_to_drive(bytes_data, "PALLET")

                # PT list → fill to 4 columns
                pt_vals = st.session_state.pt_list.copy()
                while len(pt_vals) < 4:
                    pt_vals.append("")

                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                sheet.append_row([
                    now,
                    pt_vals[0],
                    pt_vals[1],
                    pt_vals[2],
                    pt_vals[3],
                    detected_count,
                    pallet_count,
                    pallet_link
                ])

                st.success("✅ บันทึกข้อมูลเรียบร้อยแล้ว!")

            except Exception as e:
                st.error(f"❌ เกิดข้อผิดพลาด: {e}")
