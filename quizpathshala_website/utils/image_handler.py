<<<<<<< HEAD
import os

def save_image(file, file_id):
    folder = "data/images"
    os.makedirs(folder, exist_ok=True)

    path = f"{folder}/{file_id}.jpg"

    file.download_to_drive(path)

=======
import os

def save_image(file, file_id):
    folder = "data/images"
    os.makedirs(folder, exist_ok=True)

    path = f"{folder}/{file_id}.jpg"

    file.download_to_drive(path)

>>>>>>> 72286ff2e6294b7e17af827ebd9e336761c26627
    return path