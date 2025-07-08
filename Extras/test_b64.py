import base64, os

def convert_image_to_base64(file) -> str:

    """Convert uploaded image to base64 string with data URI prefix."""
    content = file.read()
    base64_encoded_image = base64.b64encode(content).decode("utf-8")
    mime_type = file.content_type
    if not mime_type:
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension == ".jpg" or file_extension == ".jpeg":
            mime_type = "image/jpeg"
        elif file_extension == ".png":
            mime_type = "image/png"
        elif file_extension == ".gif":
            mime_type = "image/gif"

    if not mime_type:
        mime_type = "application/octet-stream"
    return f"data:{mime_type};base64,{base64_encoded_image}"

with open("neck_ray.JPG", "rb") as f:
    b64_string = convert_image_to_base64(f)
    print(b64_string)