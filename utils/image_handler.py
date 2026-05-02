import os

def save_image(file, file_id):
    folder = "data/images"
    os.makedirs(folder, exist_ok=True)

    path = f"{folder}/{file_id}.jpg"

    file.download_to_drive(path)

    return path