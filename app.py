import os
import requests
import zipfile
from urllib.parse import urljoin, urlparse
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import openpyxl


# Flask app setup
app = Flask(__name__)
CORS(app)

# Use Render's writable directory for output
OUTPUT_DIRECTORY = "/tmp/output"


def create_directory(folder_name):
    """Create directory if it doesn't exist."""
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)


def download_file(url, folder_name, fallback_format="unknown"):
    """Download a file from a URL."""
    try:
        filename = os.path.basename(url.split("?")[0]) or f"image_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        if "." in filename:
            extension = filename.split(".")[-1].lower()
        else:
            extension = None

        # Send request and figure out MIME type
        with requests.get(url, stream=True, timeout=10) as response:
            response.raise_for_status()
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
                    extension = fallback_format

            # Prepare output file path
            format_folder = os.path.join(folder_name, extension)
            create_directory(format_folder)
            file_path = os.path.join(format_folder, f"{os.path.splitext(filename)[0]}.{extension}")
            with open(file_path, "wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)

        print(f"Downloaded: {file_path}")
        return file_path
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return None


def extract_images_and_metadata(url, output_folder):
    """Extract images and metadata from the given URL."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Extract page title
        title = soup.title.string if soup.title else "No Title Available"

        # Create a subfolder for the project
        project_name = urlparse(url).path.strip("/").split("/")[-1] or "default_project"
        project_folder = os.path.join(output_folder, project_name)
        create_directory(project_folder)

        # Extract image URLs
        img_tags = soup.find_all("img")
        img_urls = [
            urljoin(url, img.get("src") or img.get("data-src") or img.get("data-lazy-src"))
            for img in img_tags if img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        ]

        # Download images
        downloaded_images = []
        for img_url in img_urls:
            file_path = download_file(img_url, project_folder)
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
    """Save metadata into an Excel file."""
    excel_file_path = os.path.join(output_folder, "Scraped_Data.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Scraped Data"
    ws.append(["URL", "Title", "Project Name", "Image Count", "Folder Location", "Error?"])
    for entry in data:
        ws.append([
            entry["url"],
            entry.get("title", "No Title"),
            entry.get("project_name", ""),
            entry.get("image_count", 0),
            entry.get("project_folder", ""),
            "Yes" if "error" in entry else "No"
        ])
    wb.save(excel_file_path)
    return excel_file_path


def create_zip(output_folder):
    """Compress output folder into a ZIP."""
    zip_file_path = os.path.join(OUTPUT_DIRECTORY, f"Scraped_Data_{datetime.now().strftime('%Y%m%d%H%M%S')}.zip")
    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(output_folder):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, output_folder)
                zipf.write(full_path, arcname)
    return zip_file_path


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/scrape", methods=["POST"])
def scrape():
    """Main scraping endpoint."""
    urls = request.json.get("urls", [])
    if not urls:
        return jsonify({"error": "No URLs provided."}), 400

    # Use /tmp/output for temporary files
    output_folder = os.path.join(OUTPUT_DIRECTORY, f"scraped_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    create_directory(output_folder)

    results = []
    for url in urls:
        result = extract_images_and_metadata(url, output_folder)
        results.append(result)

    # Save to Excel
    excel_file_path = save_to_excel(results, output_folder)

    # Create ZIP file
    zip_file_path = create_zip(output_folder)

    # Return response with download details
    return jsonify({
        "message": "Scraping completed!",
        "zip_file_path": zip_file_path,
        "results": results,
    })


@app.route("/download", methods=["GET"])
def download():
    """Serve the ZIP file for downloading."""
    zip_file_path = request.args.get("path")
    if not zip_file_path or not os.path.exists(zip_file_path):
        return jsonify({"error": "File not found."}), 404
    return send_file(zip_file_path, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)