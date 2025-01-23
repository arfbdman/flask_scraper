import os
import requests
import zipfile
from urllib.parse import urljoin, urlparse
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask, request, render_template, jsonify, send_file
from flask_cors import CORS
import openpyxl


app = Flask(__name__)
CORS(app)

# Set output directory to /app/output to work with the Docker volume
OUTPUT_DIRECTORY = "/app/output"


def create_directory(folder_name):
    """Create directory if it doesn't exist."""
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)


def download_file(url, folder_name, fallback_format="unknown"):
    """Download a file from a URL and save to the specified folder."""
    try:
        # Step 1: Extract the filename and clean query parameters
        filename = os.path.basename(url.split("?")[0]) or f"image_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Step 2: Detect the extension (default to fallback if none is valid)
        if "." in filename:
            extension = filename.split(".")[-1].lower()
        else:
            extension = None

        # Step 3: Make the HTTP request and validate MIME type
        with requests.get(url, stream=True, timeout=10) as response:
            response.raise_for_status()

            # If no extension or invalid file type, inspect MIME type from headers
            if not extension or extension not in ["jpg", "jpeg", "png", "gif", "bmp", "webp"]:
                content_type = response.headers.get("Content-Type", "").lower()
                if "jpeg" in content_type:
                    extension = "jpg"
                elif "png" in content_type:
                    extension = "png"
                elif "gif" in content_type:
                    extension = "gif"
                elif "bmp" in content_type:
                    extension = "bmp"
                elif "webp" in content_type:
                    extension = "webp"
                else:
                    extension = fallback_format  # Use "unknown" if type is unsupported

            # Step 4: Create format subfolder (like jpg, png, etc.)
            format_folder = os.path.join(folder_name, extension)
            create_directory(format_folder)  # Ensure directory exists

            # Step 5: Save the file to the appropriate folder
            file_path = os.path.join(format_folder, filename if filename.endswith(f".{extension}") else f"{filename}.{extension}")
            with open(file_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)

        print(f"Downloaded: {file_path}")
        return file_path

    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return None


def extract_images_and_metadata(url, output_folder):
    """Extract and process images and metadata from the webpage."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Extract page title
        title = soup.title.string if soup.title else "No Title Available"

        # Create folder for the project
        project_name = urlparse(url).path.strip("/").split("/")[-1] or "default_project"
        project_folder = os.path.join(output_folder, project_name)
        create_directory(project_folder)

        img_tags = soup.find_all("img")
        img_urls = [
            urljoin(url, img.get("src") or img.get("data-src") or img.get("data-lazy-src"))
            for img in img_tags if img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        ]

        downloaded_images = []
        for img_url in img_urls:
            extension = os.path.splitext(img_url)[-1].lstrip(".").lower()
            extension = extension if extension in ["jpg", "jpeg", "png", "gif", "bmp", "webp"] else "unknown"
            file_path = download_file(img_url, project_folder, extension)
            if file_path:
                downloaded_images.append(file_path)

        return {
            "url": url,
            "title": title,
            "project_name": project_name,
            "image_count": len(downloaded_images),
            "project_folder": project_folder,
        }
    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        return {"url": url, "error": str(e)}


def save_to_excel(data, output_folder):
    """Save scraping results to an Excel file."""
    excel_file_path = os.path.join(output_folder, "Scraped_Data.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Scraped Data"

    # Add headers
    ws.append(["URL", "Title", "Project Name", "Image Count", "Folder Location", "Error?"])

    for entry in data:
        ws.append([
            entry["url"],
            entry.get("title", "No Title"),
            entry.get("project_name", "No Project"),
            entry.get("image_count", 0),
            entry.get("project_folder", "N/A"),
            "Yes" if "error" in entry else "No"
        ])

    wb.save(excel_file_path)
    return excel_file_path


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/scrape", methods=["POST"])
def scrape():
    urls = request.json.get("urls", [])
    if not urls:
        return jsonify({"error": "No URLs provided."}), 400

    output_folder = os.path.join(OUTPUT_DIRECTORY, f"Downloaded_Media_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}")
    create_directory(output_folder)

    results = []
    for url in urls:
        result = extract_images_and_metadata(url, output_folder)
        results.append(result)

    # Save results to Excel
    save_to_excel(results, output_folder)

    # Create ZIP file
    zip_file_path = create_zip(output_folder)

    return jsonify({
        "message": "Scraping completed!",
        "zip_file": zip_file_path,
        "results": results,
    })


@app.route("/download_zip", methods=["GET"])
def download_zip():
    zip_path = request.args.get("path")
    if not os.path.exists(zip_path):
        return jsonify({"error": "ZIP file not found."}), 404
    return send_file(zip_path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)