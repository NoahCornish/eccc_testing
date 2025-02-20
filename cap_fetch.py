import os
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import json

# Base CAP alerts directory
BASE_CAP_URL = "https://dd.weather.gc.ca/alerts/cap/"
REGION = "CWTO"

# Define paths for saving files
CAP_SAVE_PATH = "cap_alerts/"
JSON_SAVE_PATH = "JSON_ALERTS/"
ACTIVE_ALERTS_FILE = os.path.join(JSON_SAVE_PATH, "active_alerts.json")

# Ensure directories exist
os.makedirs(CAP_SAVE_PATH, exist_ok=True)
os.makedirs(JSON_SAVE_PATH, exist_ok=True)

# Step 1: Get the latest available CAP date
def get_latest_cap_date():
    response = requests.get(BASE_CAP_URL)
    if response.status_code != 200:
        print("⚠️ Unable to access the CAP main directory.")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    dates = [link.get("href").strip("/") for link in soup.find_all("a") if link.get("href").strip("/").isdigit()]
    
    return max(dates) if dates else None

# Step 2: Get available hourly subdirectories
def get_hourly_folders(cap_date):
    region_url = f"{BASE_CAP_URL}{cap_date}/{REGION}/"
    response = requests.get(region_url)
    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    return [link.get("href").strip("/") for link in soup.find_all("a") if link.get("href").strip("/").isdigit()]

# Step 3: Get CAP XML files from hourly folders
def get_cap_files(cap_date, hourly_folders):
    cap_files = []
    for hour in hourly_folders:
        cap_url = f"{BASE_CAP_URL}{cap_date}/{REGION}/{hour}/"
        response = requests.get(cap_url)
        if response.status_code != 200:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        cap_files.extend([cap_url + link.get("href") for link in soup.find_all("a") if link.get("href").endswith(".cap")])

    return cap_files

# Step 4: Download CAP files
def download_cap_files(file_urls):
    saved_files = []
    
    for file_url in file_urls:
        file_name = file_url.split("/")[-1]
        file_path = os.path.join(CAP_SAVE_PATH, file_name)

        response = requests.get(file_url)
        if response.status_code == 200:
            with open(file_path, "wb") as file:
                file.write(response.content)
            saved_files.append(file_path)

    return saved_files

# Step 5: Convert CAP XML files to JSON
def parse_cap_to_json(cap_file_path):
    tree = ET.parse(cap_file_path)
    root = tree.getroot()
    namespace = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}

    # Select English version if available
    info_blocks = root.findall("cap:info", namespace)
    selected_info = next((info for info in info_blocks if info.find("cap:language", namespace) is not None and "en" in info.find("cap:language", namespace).text), info_blocks[0] if info_blocks else None)

    if selected_info is None:
        return {}

    # Extract key details
    alert_info = {
        "identifier": root.find("cap:identifier", namespace).text if root.find("cap:identifier", namespace) is not None else "N/A",
        "sender": root.find("cap:sender", namespace).text if root.find("cap:sender", namespace) is not None else "N/A",
        "sent": root.find("cap:sent", namespace).text if root.find("cap:sent", namespace) is not None else "N/A",
        "status": root.find("cap:status", namespace).text if root.find("cap:status", namespace) is not None else "N/A",
        "msgType": root.find("cap:msgType", namespace).text if root.find("cap:msgType", namespace) is not None else "N/A",
        "scope": root.find("cap:scope", namespace).text if root.find("cap:scope", namespace) is not None else "N/A",
        "references": root.find("cap:references", namespace).text if root.find("cap:references", namespace) is not None else "N/A",
        "headline": selected_info.find("cap:headline", namespace).text if selected_info.find("cap:headline", namespace) is not None else "N/A",
        "event": selected_info.find("cap:event", namespace).text if selected_info.find("cap:event", namespace) is not None else "N/A",
        "urgency": selected_info.find("cap:urgency", namespace).text if selected_info.find("cap:urgency", namespace) is not None else "N/A",
        "severity": selected_info.find("cap:severity", namespace).text if selected_info.find("cap:severity", namespace) is not None else "N/A",
        "certainty": selected_info.find("cap:certainty", namespace).text if selected_info.find("cap:certainty", namespace) is not None else "N/A",
        "effective": selected_info.find("cap:effective", namespace).text if selected_info.find("cap:effective", namespace) is not None else "N/A",
        "expires": selected_info.find("cap:expires", namespace).text if selected_info.find("cap:expires", namespace) is not None else "N/A",
        "description": selected_info.find("cap:description", namespace).text if selected_info.find("cap:description", namespace) is not None else "N/A",
        "instruction": selected_info.find("cap:instruction", namespace).text if selected_info.find("cap:instruction", namespace) is not None else "N/A",
        "affected_areas": []
    }

    # Extract affected areas & polygons
    for area in selected_info.findall("cap:area", namespace):
        area_data = {
            "area_description": area.find("cap:areaDesc", namespace).text if area.find("cap:areaDesc", namespace) is not None else "N/A",
            "polygon": []
        }

        polygon_elem = area.find("cap:polygon", namespace)
        if polygon_elem is not None:
            coordinates = polygon_elem.text.strip().split(" ")
            area_data["polygon"] = [{"lat": float(coord.split(",")[0]), "lon": float(coord.split(",")[1])} for coord in coordinates]

        alert_info["affected_areas"].append(area_data)

    return alert_info

# Step 6: Process each CAP file and save as JSON
def convert_to_json(cap_files):
    active_alerts = []
    
    for cap_file in cap_files:
        alert_data = parse_cap_to_json(cap_file)
        if not alert_data:
            continue

        json_filename = os.path.basename(cap_file).replace(".cap", ".json")
        json_file_path = os.path.join(JSON_SAVE_PATH, json_filename)

        with open(json_file_path, "w", encoding="utf-8") as json_file:
            json.dump(alert_data, json_file, indent=4, ensure_ascii=False)

        active_alerts.append(alert_data)

    # Overwrite active_alerts.json with all current alerts
    with open(ACTIVE_ALERTS_FILE, "w", encoding="utf-8") as json_file:
        json.dump({"alerts": active_alerts}, json_file, indent=4, ensure_ascii=False)

    return active_alerts

# Step 7: Cleanup expired alerts
def cleanup_folders():
    for folder in [CAP_SAVE_PATH, JSON_SAVE_PATH]:
        for file in os.listdir(folder):
            file_path = os.path.join(folder, file)
            os.remove(file_path)

# Step 8: Run the process
latest_date = get_latest_cap_date()
if latest_date:
    hourly_folders = get_hourly_folders(latest_date)
    if hourly_folders:
        cap_files = get_cap_files(latest_date, hourly_folders)
        if cap_files:
            downloaded_files = download_cap_files(cap_files)
            if downloaded_files:
                active_alerts = convert_to_json(downloaded_files)
                if not active_alerts:
                    cleanup_folders()
                else:
                    print(f"✅ {len(active_alerts)} active alerts saved.")
