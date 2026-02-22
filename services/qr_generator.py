import qrcode
import os
from flask import current_app

def generate_table_qr(table_id):
    """
    Generates a high-quality QR code for a specific table.
    The QR points to the mobile menu with the table ID as a parameter.
    """
    # 1. Define the URL the QR code will open
    # In production, replace 'localhost:5000' with your actual domain
    base_url = os.getenv('BASE_URL', 'http://127.0.0.1:5000')
    target_url = f"{base_url}/menu?table={table_id}"

    # 2. Configure QR Code looks
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(target_url)
    qr.make(fit=True)

    # 3. Create the image
    img = qr.make_image(fill_color="black", back_color="white")

    # 4. Save path logic
    # We save it in static/qrcodes so Flask can serve it as an image
    folder_path = os.path.join(current_app.root_path, 'static', 'qrcodes')
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    filename = f"table_{table_id}.png"
    file_path = os.path.join(folder_path, filename)
    
    img.save(file_path)
    
    # Return the relative path for the database/frontend
    return f"qrcodes/{filename}"