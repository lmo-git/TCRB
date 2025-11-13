import streamlit as st
from PIL import Image
import numpy as np
import uuid
import datetime
import gspread
import requests
from pyzbar.pyzbar import decode
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# ======================================================
# STYLE: Make Camera Bigger for Android
# ======================================================
st.markdown(
    """
    <style>
    /* Make camera preview bigger */
    div[data-testid="stCameraInput"] video {
        width: 100% !important;
        height: 100vh !important;
        object-fit: cover !important;
        transform: scale(1.1); /* enlarge */
        transform-origin: center;
    }

    /* Enlarge capture button */
    div[data-testid="stCameraInput"] button {
        transform: scale(1.4);
        padding: 15px 25px;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# ======================================================
# TITLE
# ======================================================
st.title("📦 AI นับพาเลทสำหรับโรงงาน TCRB")


# ======================================================
# SESSION INIT
# ======================================================
if "page" not in st.session_state:
    st.session_state.page = "page1"

if "barcode_list" not in st.session_state:
    st.session_state.barcode_list = []


# ======================================================
# PAGE 1 — BARCODE SCAN
# ======================================================
if st.session_state.page == "page1":

    st.header("📄 ขั้นตอนที่ 1: สแกน Barcode ใบคุมพาเลท (สูงสุด 4 อัน)")

    barcode_image = st.camera_input("📸 ถ่าย Barcode")

    if barcode_image:
        img = Image.open(barcode_image).convert("RGB")
        img_np = np.array(img)

        decoded = decode(img_np)

        if decoded:
            for bc in decoded:
                code = bc.data.decode("utf-8")
                if code not in st.session_state.barcode_list:
                    if len(st.session_state.barcode_list) < 4:
                        st.session_state.barcode_list.append(code)
                        st.success(f"สแกนสำเร็จ: {code}")
                    else:
                        st.warning("❗ สแกนได้สูงสุด 4 barcode เท่านั้น")
        else:
            st.error("❌ ไม่พบ Barcode ในภาพ")


    # Show list
    st.subheader("📌 รายการ Barcode ที่สแกนแล้ว:")
    if st.session_state.barcode_list:
        for i, bc in enumerate(st.session_state.barcode_list, 1):
            st.write(f"{i}. **{bc}**")
    else:
        st.info("ยังไม่มี Barcode")

    # Clear list
    if st.button("🗑 ล้างทั้งหมด"):
        st.session_state.barcode_list = []
        st.rerun()

    # Next page
    if st.button("➡️ ถัดไป (ไปถ่ายรูปพาเลท)"):
        if len(st.session_state.barcode_list) == 0:
            st.warning("⚠️ กรุณาสแกน Barcode อย่างน้อย 1 รายการ")
        else:
            st.session_state.page = "page2"
            st.rerun()


# ======================================================
# PAGE 2 — PALLET DETECTION
# ======================================================
elif st.session_state.page == "page2":

    st.header("📦 ขั้นตอนที่ 2: ถ่ายรูปพาเลทเพื่อตรวจจับ")

    st.subheader("📌 Barcode ใบคุมพาเลท:")
    for bc in st.session_state.barcode_list:
        st.code(bc)

    pallet_image = st.camera_input("📸 ถ่ายพาเลท 1 ด้าน")

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
            resp_data = response.json()
            predictions = resp_data.get("predictions", [])
            detected_count = len(predictions)

            st.success(f"🎯 ตรวจจับพาเลทได้ {detected_count} ชิ้น")

        except Exception as e:
            st.error(f"เกิดข้อผิดพลาด: {e}")

    pallet_count = st.number_input("จำนวนพาเลทที่ยืนยัน:", value=detected_count, step=1)


    # Back
    if st.button("⬅️ กลับไปสแกน Barcode"):
        st.session_state.page = "page1"
        st.rerun()


    # ======================================================
    # SAVE BUTTON — SAVE TO GOOGLE SHEET + GOOGLE DRIVE
    # ======================================================
    if st.button("✅ ยืนยันและบันทึก"):

        try:
            # AUTH
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_info(st.secrets["gcp"], scopes=scopes)
            gc = gspread.authorize(creds)
            sheet = gc.open_by_key("1GR4AH-WFQCA9YGma6g3t0APK8xfMW8DZZkBQAqHWg68").sheet1
            drive_service = build("drive", "v3", credentials=creds)

            # Create / get folder
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
                if file_bytes is None:
                    return "NO_IMAGE"

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

            # Prepare sheet row
            barcodes = st.session_state.barcode_list.copy()
            while len(barcodes) < 4:
                barcodes.append("")

            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sheet.append_row([
                now,
                barcodes[0],
                barcodes[1],
                barcodes[2],
                barcodes[3],
                detected_count,
                pallet_count,
                pallet_link
            ])

            st.success("✅ บันทึกข้อมูลเรียบร้อยแล้ว!")

        except Exception as e:
            st.error(f"❌ บันทึกข้อมูลไม่สำเร็จ: {e}")
