import os
import requests
import zipfile
from time import sleep
from urllib.parse import urljoin, urlparse
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import openpyxl


# Flask app setup
app = Flask(__name__)
CORS(app)

# Use Render's writable temporary directory
OUTPUT_DIRECTORY = "/tmp/output"

# Headers to mimic a real browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0 Safari/537.36"
}


def create_directory(folder_name):
    """Create directory if it doesn't exist."""
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)


def download_file(url, folder_name, fallback_format="unknown"):
    """Download a file from a URL."""
    try:
        # Extract the filename and extension
        filename = os.path.basename(url.split("?")[0]) or f"image_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        if "." in filename:
            extension = filename.split(".")[-1].lower()
        else:
            extension = None

        # Fetch the image with headers
        with requests.get(url, stream=True, timeout=10, headers=HEADERS) as response:
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

            # Save file to appropriate folder
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
    """Extract images and metadata from a webpage."""
    try:
        response = requests.get(url, timeout=10, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Extract page title and project name
        title = soup.title.string if soup.title else "No Title Available"
        project_name = urlparse(url).path.strip("/").split("/")[-1] or "default_project"

        # Create project folder
        project_folder = os.path.join(output_folder, project_name)
        create_directory(project_folder)

        # Find image URLs
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
            "project_folder": project_folder
        }
    except requests.exceptions.RequestException as e:
        print(f"Error processing URL {url}: {e}")
        return {"url": url, "error": str(e)}


def save_to_excel(data, output_folder):
    """Save scraping metadata to an Excel file."""
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
    """Create a ZIP file of the entire output folder."""
    zip_file_path = os.path.join(OUTPUT_DIRECTORY, f"Scraped_Data_{datetime.now().strftime('%Y%m%d%H%M%S')}.zip")
    with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(output_folder):
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, output_folder)  # Keep the folder structure inside the ZIP
                zipf.write(full_path, arcname)
    print(f"ZIP File Created: {zip_file_path}")
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

    # Create a unique folder for this scrape job
    output_folder = os.path.join(OUTPUT_DIRECTORY, f"scraped_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    create_directory(output_folder)

    # Process all URLs
    results = []
    for url in urls:
        result = extract_images_and_metadata(url, output_folder)
        results.append(result)

        # Add a delay between requests
        sleep(1)

    # Save metadata to Excel and create ZIP archive
    save_to_excel(results, output_folder)
    zip_file_path = create_zip(output_folder)

    return jsonify({
        "message": "Scraping completed!",
        "zip_file_path": zip_file_path,
        "results": results,
    })


@app.route("/download", methods=["GET"])
def download():
    """Serve the ZIP output file for download."""
    zip_file_path = request.args.get("path")
    if not zip_file_path or not os.path.exists(zip_file_path):
        return jsonify({"error": "File not found."}), 404
    return send_file(zip_file_path, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)