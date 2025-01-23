import os
import requests
from time import sleep
from urllib.parse import urljoin, urlparse
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask, render_template, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
import openpyxl


# Flask setup
app = Flask(__name__)
CORS(app)

# Directory for temporary file output (writable on Render)
OUTPUT_DIRECTORY = "/tmp/output"

# Headers to mimic a real browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0 Safari/537.36"
}


def create_directory(folder_name):
    """Create a directory if it doesn't exist."""
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)


def download_file(url, folder_name, fallback_extension="unknown"):
    """Download a file from a URL."""
    try:
        # Extract the filename
        filename = os.path.basename(url.split("?")[0]) or f"image_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        if "." in filename:
            extension = filename.split(".")[-1].lower()
        else:
            extension = None

        # Send request with headers
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        # Determine file extension by MIME type if necessary
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
                extension = fallback_extension

        # Save file to correct folder
        format_folder = os.path.join(folder_name, extension)
        create_directory(format_folder)
        file_path = os.path.join(format_folder, f"{os.path.splitext(filename)[0]}.{extension}")

        with open(file_path, "wb") as file:
            file.write(response.content)

        print(f"Downloaded: {file_path}")
        return file_path
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return None


def extract_images_and_metadata(url, output_folder):
    """Extract images and metadata from a webpage."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Extract page title
        title = soup.title.string if soup.title else "No Title Available"

        # Extract project name
        project_name = urlparse(url).path.strip("/").split("/")[-1] or "default_project"
        project_folder = os.path.join(output_folder, project_name)
        create_directory(project_folder)

        # Extract image URLs
        img_tags = soup.find_all("img")
        img_urls = [
            urljoin(url, img.get("src") or img.get("data-src") or img.get("data-lazy-src"))
            for img in img_tags if img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        ]

        # Download all images
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
            "downloaded_images": downloaded_images
        }
    except requests.exceptions.RequestException as e:
        print(f"Error processing URL {url}: {e}")
        return {"url": url, "error": str(e)}


def save_to_excel(data, output_folder):
    """Save scraping results to an Excel file."""
    excel_file_path = os.path.join(output_folder, "Scraped_Data.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Scraped Data"
    ws.append(["URL", "Title", "Project Name", "Image Count", "Error?"])
    for entry in data:
        ws.append([
            entry["url"],
            entry.get("title", "No Title"),
            entry.get("project_name", ""),
            entry.get("image_count", 0),
            "Yes" if "error" in entry else "No"
        ])
    wb.save(excel_file_path)
    return excel_file_path


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/scrape", methods=["POST"])
def scrape():
    """Main scraping endpoint."""
    urls = request.json.get("urls", [])
    if not urls:
        return jsonify({"error": "No URLs provided."}), 400

    # Unique folder for this scrape session
    output_folder = os.path.join(OUTPUT_DIRECTORY, f"scraped_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    create_directory(output_folder)

    # Process each URL
    results = []
    all_files = []
    for url in urls:
        result = extract_images_and_metadata(url, output_folder)
        results.append(result)

        # Add downloaded image paths to all_files
        if "downloaded_images" in result:
            all_files.extend(result["downloaded_images"])

        # Delay to mimic human behavior
        sleep(1)

    # Save metadata into an Excel file
    excel_file_path = save_to_excel(results, output_folder)
    all_files.append(excel_file_path)

    # Generate download URLs for each file
    download_links = [
        f"/file-download?file_path={file}" for file in all_files
    ]

    return jsonify({
        "message": "Scraping completed!",
        "download_links": download_links,
        "results": results
    })


@app.route("/file-download", methods=["GET"])
def file_download():
    """Download a specific file."""
    file_path = request.args.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File not found."}), 404
    directory, filename = os.path.split(file_path)
    return send_from_directory(directory, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)