import streamlit as st
from PIL import Image
import numpy as np
import uuid
import datetime
import gspread
import requests
import re
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
# Extract PT number
# ======================================================
def extract_pt_number(text):
    """
    รับข้อความ เช่น 'PT68020045'
    → คืนค่า '68020045'
    """
    text = text.upper().strip()
    match = re.search(r"PT(\d+)", text)
    if match:
        return match.group(1)
    return None


# ฟังก์ชันเพิ่ม PT
def add_pt_manual(pt_text):
    pt = extract_pt_number(pt_text)
    if pt:
        if pt not in st.session_state.pt_list:
            if len(st.session_state.pt_list) < 4:
                st.session_state.pt_list.append(pt)
                st.success(f"เพิ่ม PT: PT{pt}")
            else:
                st.warning("เพิ่มได้สูงสุด 4 PT เท่านั้น")
        else:
            st.info("เลขนี้มีอยู่แล้ว")
    else:
        st.error("❌ กรุณาพิมพ์รูปแบบ PTxxxxxxx เช่น PT68020045")


# ======================================================
# PAGE 1 — Manual PT Input (NOT REQUIRED)
# ======================================================
if st.session_state.page == "page1":

    st.header("📄 ขั้นตอนที่ 1: กรอกเลข PT (ไม่บังคับ, สูงสุด 4 ค่า)")

    pt_input = st.text_input("พิมพ์เลข PT (เช่น PT68020045)")

    if st.button("➕ เพิ่มเลข PT"):
        add_pt_manual(pt_input)

    # แสดง PT ที่มีแล้ว
    st.subheader("📌 รายการ PT:")
    if st.session_state.pt_list:
        for i, pt in enumerate(st.session_state.pt_list, 1):
            st.write(f"{i}. PT{pt}")
    else:
        st.info("ยังไม่มี PT (ข้ามได้)")

    # ปุ่มล้าง
    if st.button("🗑 ล้าง PT ทั้งหมด"):
        st.session_state.pt_list = []
        st.rerun()

    # ไปหน้า 2 (ไม่บังคับให้มี PT)
    if st.button("➡️ ถัดไป (ไปถ่ายพาเลท)"):
        st.session_state.page = "page2"
        st.rerun()


# ======================================================
# PAGE 2 — PALLET DETECTION
# ======================================================
elif st.session_state.page == "page2":

    st.header("📦 ขั้นตอนที่ 2: ตรวจนับพาเลท")

    st.subheader("📌 PT ที่บันทึกแล้ว:")
    if st.session_state.pt_list:
        for pt in st.session_state.pt_list:
            st.code(f"PT{pt}")
    else:
        st.info("ไม่มี PT (ข้ามได้)")

    pallet_image = st.camera_input("📸 ถ่ายรูปพาเลท")

    detected_count = 0
    bytes_data = None

    if pallet_image:
        bytes_data = pallet_image.getvalue()

        with open("pallet_temp.jpg", "wb") as f:
            f.write(bytes_data)

        try:
            response = requests.post(
                "https://detect.roboflow.com/pallet-detection-measurement/1?api_key=WtsFf6wpMhlX16yRNb6e",
                files={"file": open("pallet_temp.jpg", "rb")},
                timeout=20
            )
            preds = response.json().get("predictions", [])
            detected_count = len(preds)

            st.success(f"🎯 AI ตรวจจับพาเลทได้ {detected_count} กอง")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาด: {e}")

    pallet_count = st.number_input("จำนวนพาเลทที่ต้องการยืนยัน:", value=detected_count, step=1)

    # ปุ่มย้อนกลับ
    if st.button("⬅️ กลับไปกรอก PT"):
        st.session_state.page = "page1"
        st.rerun()


    # ======================================================
    # SAVE DATA
    # ======================================================
    if st.button("✅ ยืนยันและบันทึกข้อมูล"):

        if bytes_data is None:
            st.warning("⚠ กรุณาถ่ายรูปพาเลทก่อน")
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

                # หาโฟลเดอร์
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
                    fname = f"{prefix}_{uuid.uuid4().hex}.jpg"
                    with open(fname, "wb") as f:
                        f.write(file_bytes)

                    media = MediaFileUpload(fname, mimetype="image/jpeg")
                    uploaded = drive_service.files().create(
                        body={"name": fname, "parents": [folder_id]},
                        media_body=media,
                        fields="id"
                    ).execute()

                    return f"https://drive.google.com/file/d/{uploaded['id']}/view"

                # Upload pallet image
                pallet_link = upload_to_drive(bytes_data, "PALLET")

                # PT list → fill to 4 columns
                pt_vals = st.session_state.pt_list.copy()
                while len(pt_vals) < 4:
                    pt_vals.append("")

                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Append row into Google Sheet
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
