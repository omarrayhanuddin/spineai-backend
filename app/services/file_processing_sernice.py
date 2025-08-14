import asyncio
from fastapi import UploadFile, HTTPException
import pydicom
# import fitz   # Removed to avoid PyMuPDF DLL errors
import io
import base64
from typing import List, Dict
from PIL import Image
import numpy as np
import os

class FileProcessingService:
    """Service class to process various file types and return base64 data with data URI prefix, file type, metadata, filename, and S3 URLs."""

    SUPPORTED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}
    SUPPORTED_DICOM_EXTENSIONS = {"dcm", "dicom"}
    SUPPORTED_PDF_EXTENSIONS = {"pdf"}

    @staticmethod
    async def convert_image_to_base64(file: UploadFile, index: int) -> List[Dict]:
        """Convert image file to base64 with data URI prefix."""
        content = await file.read()
        base64_encoded_image = base64.b64encode(content).decode("utf-8")
        mime_type = file.content_type
        if not mime_type:
            file_extension = os.path.splitext(file.filename)[1].lower()
            mime_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif"
            }.get(file_extension, "application/octet-stream")
        
        base64_data = f"data:{mime_type};base64,{base64_encoded_image}"
        return [{
            "base64_data": base64_data,
            "file_type": "image",
            "metadata": {},
            "filename": file.filename,
            "original_index": index
        }]

    @staticmethod
    async def process_dicom(file: UploadFile, index: int) -> List[Dict]:
        """Process DICOM file and return base64 image (if applicable) with data URI prefix and metadata."""
        content = await file.read()
        try:
            dicom = pydicom.dcmread(io.BytesIO(content))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid DICOM file: {e}")
        
        metadata = {
            "PatientID": getattr(dicom, "PatientID", ""),
            "StudyDescription": getattr(dicom, "StudyDescription", ""),
            "Modality": getattr(dicom, "Modality", ""),
        }
        base64_data = None
        
        if hasattr(dicom, "PixelData"):
            pixel_array = dicom.pixel_array
            pixel_array = ((pixel_array - pixel_array.min()) / (pixel_array.max() - pixel_array.min() + 1e-10) * 255).astype(np.uint8)
            image = Image.fromarray(pixel_array)
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            base64_encoded_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
            base64_data = f"data:image/png;base64,{base64_encoded_image}"
        
        return [{
            "base64_data": base64_data,
            "file_type": "dicom",
            "metadata": metadata,
            "filename": file.filename,
            "original_index": index
        }]

    @staticmethod
    async def process_pdf(file: UploadFile, index: int) -> List[Dict]:
        """
        Dummy PDF processor — skips actual PDF to image conversion
        to avoid PyMuPDF dependency errors during development.
        """
        return [{
            "base64_data": None,
            "file_type": "pdf",
            "metadata": {"note": "PDF processing disabled in dev mode"},
            "filename": file.filename,
            "original_index": index
        }]

    @classmethod
    async def process_files(cls, files: List[UploadFile], s3_urls: List[str]) -> List[Dict]:
        """Process a list of files and return base64 data with data URI prefix, file type, metadata, filename, and S3 URLs."""
        if not files:
            return []
        
        if not s3_urls:
            raise HTTPException(
                status_code=400,
                detail="S3 URLs must be provided for all files"
            )

        if len(files) != len(s3_urls):
            raise HTTPException(
                status_code=400,
                detail=f"Number of files ({len(files)}) does not match number of S3 URLs ({len(s3_urls)})"
            )

        tasks = []
        for idx, file in enumerate(files):
            ext = file.filename.lower().split(".")[-1]
            if ext in cls.SUPPORTED_IMAGE_EXTENSIONS:
                tasks.append(cls.convert_image_to_base64(file, idx))
            elif ext in cls.SUPPORTED_DICOM_EXTENSIONS:
                tasks.append(cls.process_dicom(file, idx))
            elif ext in cls.SUPPORTED_PDF_EXTENSIONS:
                tasks.append(cls.process_pdf(file, idx))
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type: {ext}"
                )

        # Gather results concurrently
        results = await asyncio.gather(*tasks)
        
        # Flatten and sort by original_index to preserve order
        output = []
        for result in results:
            output.extend(result)
        output.sort(key=lambda x: (x["original_index"], x.get("metadata", {}).get("page_number", 1)))

        # Assign S3 URLs based on original_index
        for item in output:
            item["s3_url"] = s3_urls[item["original_index"]]
            del item["original_index"]

        return output
