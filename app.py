import os
import requests
from urllib.parse import urljoin, urlparse
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
import openpyxl
from time import sleep


# Flask setup
app = Flask(__name__)
CORS(app)

# Determine your local Downloads folder
DOWNLOAD_DIRECTORY = os.path.join(os.path.expanduser("~"), "Downloads", "Scraper_Output")

# User-Agent header to mimic browser requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0 Safari/537.36"
}

# Retry settings
RETRY_COUNT = 3
RETRY_DELAY = 2  # seconds


def create_directory(folder_name):
    """Create directory if it doesn't exist."""
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)


def send_request_with_retries(url):
    """Send an HTTP GET request with retry logic."""
    for attempt in range(RETRY_COUNT):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"Request failed for {url} (attempt {attempt + 1}/{RETRY_COUNT}): {e}")
            if attempt < RETRY_COUNT - 1:
                sleep(RETRY_DELAY)
            else:
                raise e


def download_file(url, folder_name, fallback_format="unknown"):
    """Download a file from the given URL."""
    try:
        # Clean filename and determine extension
        filename = os.path.basename(url.split("?")[0]) or f"image_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        extension = None
        if "." in filename:
            extension = filename.split(".")[-1].lower()

        # Send request
        response = send_request_with_retries(url)

        # Determine extension from Content-Type if needed
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

        # Save to folder
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
    """Extract images and metadata from a URL."""
    try:
        # Fetch the webpage
        response = send_request_with_retries(url)
        soup = BeautifulSoup(response.text, "html.parser")

        # Extract metadata
        title = soup.title.string if soup.title else "No Title Available"
        project_name = urlparse(url).path.strip("/").split("/")[-1] or "default_project"

        # Create a folder for this project
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
    except requests.exceptions.RequestException as e:
        print(f"Error processing URL {url}: {e}")
        return {"url": url, "error": str(e)}


def save_to_excel(data, output_folder):
    """Save metadata and results to an Excel file."""
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
            "Yes" if "error" in entry else "No",
        ])
    wb.save(excel_file_path)
    return excel_file_path


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/scrape", methods=["POST"])
def scrape():
    """Main endpoint for scraping."""
    urls = request.json.get("urls", [])
    if not urls:
        return jsonify({"error": "No URLs provided."}), 400

    # Create output directory for the scrape
    output_folder = os.path.join(DOWNLOAD_DIRECTORY, f"scraped_{datetime.now().strftime('%Y%m%d%H%M%S')}")
    create_directory(output_folder)

    # Process all URLs
    results = []
    for url in urls:
        result = extract_images_and_metadata(url, output_folder)
        results.append(result)

        # Add delay to avoid being flagged
        sleep(1)

    # Save Excel metadata
    excel_file_path = save_to_excel(results, output_folder)

    # Return status and file paths
    return jsonify({
        "message": "Scraping completed! Files have been saved to your Downloads folder.",
        "output_folder": output_folder,
        "excel_file": excel_file_path,
        "results": results,
    })


@app.route("/download_excel", methods=["GET"])
def download_excel():
    """Serve the Excel file for download."""
    excel_file_path = request.args.get("path")
    if not excel_file_path or not os.path.exists(excel_file_path):
        return jsonify({"error": "File not found."}), 404
    return send_file(excel_file_path, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)