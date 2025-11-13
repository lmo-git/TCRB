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
# Extract ANY number
# Example:
# "PT20045" → "20045"
# "20045" → "20045"
# "คำสั่งงาน 99887 เรื่อง..." → "99887"
# No number → None
# ======================================================
def extract_number(text):
    nums = re.findall(r"\d+", text)
    if nums:
        return nums[0]   # ใช้เลขชุดแรก
    return None


# Add PT manually (no rules)
def add_pt_manual(pt_text):
    number = extract_number(pt_text)

    if number:
        if number not in st.session_state.pt_list:
            if len(st.session_state.pt_list) < 4:
                st.session_state.pt_list.append(number)
                st.success(f"เพิ่มเลข: {number}")
            else:
                st.warning("เพิ่มได้สูงสุด 4 ค่า")
        else:
            st.info("เลขนี้มีอยู่แล้ว")
    else:
        st.info("ไม่มีตัวเลขในข้อความ — ข้ามรายการนี้")


# ======================================================
# PAGE 1 — INPUT PT (optional)
# ======================================================
if st.session_state.page == "page1":

    st.header("📄 ขั้นตอนที่ 1: กรอกเลข PT (ไม่บังคับ, สูงสุด 4 ค่า)")

    pt_input = st.text_input("พิมพ์หมายเลขพาเลท")

    if st.button("➕ เพิ่มเลข"):
        add_pt_manual(pt_input)

    # แสดงรายการ PT
    st.subheader("📌 รายการเลขที่เพิ่มแล้ว:")
    if st.session_state.pt_list:
        for i, pt in enumerate(st.session_state.pt_list, 1):
            st.write(f"{i}. {pt}")
    else:
        st.info("ยังไม่มีเลข (สามารถข้ามได้)")

    # ปุ่มล้าง
    if st.button("🗑 ล้างทั้งหมด"):
        st.session_state.pt_list = []
        st.rerun()

    # ไปหน้า 2
    if st.button("➡️ ถัดไป (ไปถ่ายพาเลท)"):
        st.session_state.page = "page2"
        st.rerun()


# ======================================================
# PAGE 2 — PALLET DETECTION
# ======================================================
elif st.session_state.page == "page2":

    st.header("📦 ขั้นตอนที่ 2: ตรวจนับพาเลท")

    st.subheader("📌 เลขที่กรอกมา:")
    if st.session_state.pt_list:
        for pt in st.session_state.pt_list:
            st.code(pt)
    else:
        st.info("ไม่ได้กรอกเลข (ข้ามได้)")

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

    pallet_count = st.number_input("จำนวนพาเลทที่ยืนยัน:", value=detected_count, step=1)

    # ย้อนกลับ
    if st.button("⬅️ กลับไปกรอกเลข"):
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

                # Create/find folder
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

                # Upload image
                def upload_to_drive(file_bytes, prefix):
                    fname = f"{prefix}_{uuid.uuid4().hex}.jpg"
                    with open(fname, "wb") as f:
                        f.write(file_bytes)

                    media = MediaFileUpload(fname, mimetype="image/jpeg")
                    file_uploaded = drive_service.files().create(
                        body={"name": fname, "parents": [folder_id]},
                        media_body=media,
                        fields="id"
                    ).execute()

                    return f"https://drive.google.com/file/d/{file_uploaded['id']}/view"

                pallet_link = upload_to_drive(bytes_data, "PALLET")

                # Ensure 4 PT columns
                pt_vals = st.session_state.pt_list.copy()
                while len(pt_vals) < 4:
                    pt_vals.append("")

                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Save to Google Sheet
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
                st.error(f"❌ Error: {e}")
