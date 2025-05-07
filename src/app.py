import threading
import time
import os
import logging

import requests
from flask import Flask, jsonify, render_template, send_from_directory

# Configuration
API_URL = "https://api.thedogapi.com/v1"

app = Flask(__name__, static_folder="static")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache dictionaries with timestamps
breeds_cache = {"data": None, "timestamp": 0, "is_fetching": False}
image_cache = {}

# Available 3D models for breeds
BREED_MODELS = {
    "labrador": "labrador.glb",
    "german shepherd": "german_shepherd.glb",
    "golden retriever": "golden_retriever.glb",
    "akita": "akita.glb",
    # Add more breed-model mappings as you get them
}

DEFAULT_MODEL = "model.glb"  # Fallback model


def get_breed_model(breed_name):
    """Get the appropriate 3D model for a breed"""
    # Convert breed name to lowercase for case-insensitive matching
    breed_name = breed_name.lower()

    # Check if we have a specific model for this breed
    if breed_name in BREED_MODELS:
        model_path = f"dog/{BREED_MODELS[breed_name]}"
        # Check if the specific model exists
        if os.path.exists(os.path.join("models", model_path)):
            logger.info(f"Found model for {breed_name}: {model_path}")
            return model_path

    # Return default model if no specific model exists
    logger.info(f"No model found for {breed_name}, using default model")
    return f"dog/{DEFAULT_MODEL}"


def fetch_dog_breeds_background():
    """Background task to fetch all dog breeds and their images"""
    if breeds_cache["is_fetching"]:
        return

    breeds_cache["is_fetching"] = True

    try:
        # Fetch all breeds
        response = requests.get(f"{API_URL}/breeds")
        if response.status_code == 200:
            breeds_cache["data"] = response.json()
            breeds_cache["timestamp"] = time.time()

            # Prefetch images for all breeds
            for breed in breeds_cache["data"]:
                image_id = breed.get("reference_image_id")
                if image_id and image_id not in image_cache:
                    get_breed_image(image_id)
    finally:
        breeds_cache["is_fetching"] = False


def get_dog_breeds():
    """Fetch all dog breeds from the API with 24-hour caching"""
    current_time = time.time()

    # If cache is expired or empty, start background fetch
    if (
        breeds_cache["data"] is None
        or current_time - breeds_cache["timestamp"] >= 60 * 60 * 24
    ):
        if not breeds_cache["is_fetching"]:
            threading.Thread(target=fetch_dog_breeds_background).start()

        # If we have no data at all, wait for initial fetch
        if breeds_cache["data"] is None:
            response = requests.get(f"{API_URL}/breeds")
            if response.status_code == 200:
                breeds_cache["data"] = response.json()
                breeds_cache["timestamp"] = current_time

    return breeds_cache["data"] or []


def get_breed_image(image_id):
    """Fetch image details for a specific image ID with 24-hour caching"""
    if not image_id:
        return None

    current_time = time.time()
    if (
        image_id in image_cache
        and current_time - image_cache[image_id]["timestamp"] < 60 * 60 * 24
    ):
        return image_cache[image_id]["data"]

    response = requests.get(f"{API_URL}/images/{image_id}")
    if response.status_code == 200:
        data = response.json()
        image_cache[image_id] = {"data": data, "timestamp": current_time}
        return data
    else:
        return {"url": "https://placehold.co/600x400?text=No+image+available"}


@app.route("/")
def index():
    """Main route to display dog breeds"""
    logger.info("Fetching dog breeds...")
    breeds = get_dog_breeds()
    breed_data = []

    for breed in breeds:
        breed_data.append(
            {
                "id": breed.get("id"),
                "name": breed["name"],
                "image_id": breed.get("reference_image_id"),
                "image_url": (
                    None
                    if not breed.get("reference_image_id")
                    else f"/api/image/{breed.get('reference_image_id')}"
                ),
            }
        )

    return render_template("index.html", breeds=breed_data)


@app.route("/api/image/<image_id>")
def image_proxy(image_id):
    """API endpoint to get image URL for a specific image ID"""
    image_data = get_breed_image(image_id)
    if image_data and "url" in image_data:
        return jsonify({"url": image_data["url"]})
    return jsonify({"url": "https://placehold.co/600x400?text=No+image+available"})


@app.route("/breed/<int:breed_id>")
def breed_detail(breed_id):
    """Display detailed information about a specific breed"""
    breeds = get_dog_breeds()

    # Find the breed with the specified ID
    breed = next((b for b in breeds if b.get("id") == breed_id), None)

    if not breed:
        return render_template("error.html", message="Breed not found"), 404

    # Get the image for this breed
    image_url = None
    image_id = breed.get("reference_image_id")
    if image_id:
        image_data = get_breed_image(image_id)
        if image_data and "url" in image_data:
            image_url = image_data["url"]

    # Get the appropriate 3D model for this breed
    model_path = get_breed_model(breed["name"])

    return render_template(
        "breed_detail.html", breed=breed, image_url=image_url, model_path=model_path
    )


@app.route("/models/<path:filename>")
def serve_model(filename):
    """Serve 3D model files from the models directory"""
    return send_from_directory("models", filename)


@app.errorhandler(404)
def page_not_found(e):
    return render_template("error.html", message="Page not found"), 404


if __name__ == "__main__":
    logger.info("Starting Flask server...")
    app.run(debug=False, port=5050, host="0.0.0.0")
