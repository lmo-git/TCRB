import streamlit as st
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np
import uuid
import datetime
import gspread
import requests
import cv2
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
    /* ขยายกล้องให้ใหญ่เต็มหน้าจอมากขึ้น */
    div[data-testid="stCameraInput"] video {
        width: 100% !important;
        height: 100vh !important;
        object-fit: cover !important;
        transform: scale(1.05);
        transform-origin: center;
    }

    /* ขยายปุ่มถ่ายรูปให้ใหญ่ขึ้น */
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
st.title("📦 AI นับพาเลท + สแกน Barcode สำหรับโรงงาน TCRB")


# ======================================================
# SESSION INIT
# ======================================================
if "page" not in st.session_state:
    st.session_state.page = "page1"

if "barcode_list" not in st.session_state:
    st.session_state.barcode_list = []


# ======================================================
# PAGE 1 — BARCODE SCAN (SHARP & CLEAR)
# ======================================================
if st.session_state.page == "page1":

    st.header("📄 ขั้นตอนที่ 1: สแกน Barcode ใบคุมพาเลท (สูงสุด 4 อัน)")

    barcode_image = st.camera_input("📸 ถ่าย Barcode ให้ชัดที่สุด (เข้าใกล้ + ไม่สั่น)")

    if barcode_image:
        # โหลดรูป
        img = Image.open(barcode_image).convert("RGB")

        # 1) Sharpen
        img = img.filter(ImageFilter.SHARPEN)
        sharp_enhancer = ImageEnhance.Sharpness(img)
        img = sharp_enhancer.enhance(3.0)

        # 2) เพิ่ม contrast
        contrast_enhancer = ImageEnhance.Contrast(img)
        img = contrast_enhancer.enhance(2.0)

        # 3) Upscale (ขยายให้ใหญ่ขึ้น 2 เท่า)
        w, h = img.size
        img = img.resize((w * 2, h * 2), Image.LANCZOS)

        # 4) แปลงเป็น gray
        img_gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)

        # 5) Threshold เพื่อให้เส้นบาร์โค้ดชัดขึ้น
        _, img_thresh = cv2.threshold(
            img_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        # 6) Decode barcode
        decoded = decode(img_thresh)

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
            st.error("❌ ยังอ่าน Barcode ไม่ได้ ลองขยับให้เข้าใกล้/ไม่สั่น แล้วถ่ายใหม่")

    # แสดงรายการ barcode ที่สแกนแล้ว
