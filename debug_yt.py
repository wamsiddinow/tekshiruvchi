from googleapiclient.discovery import build
import os

API_KEY_FILE = "youtube_api_key.txt"

def debug_search():
    if not os.path.exists(API_KEY_FILE):
        print("API Key fayli yo'q")
        return

    with open(API_KEY_FILE, "r") as f:
        api_key = f.read().strip()

    youtube = build("youtube", "v3", developerKey=api_key)
    
    handle = "@Tarmoq_himoyasi"
    print(f"Qidirilmoqda: {handle}")
    
    try:
        # 1. Search
        search_response = youtube.search().list(
            q=handle, part="id,snippet", type="channel", maxResults=5
        ).execute()
        
        print("\n--- Qidiruv Natijalari ---")
        if not search_response.get("items"):
            print("Hech narsa topilmadi.")
        else:
            for item in search_response["items"]:
                print(f"ID: {item['id']['channelId']}")
                print(f"Title: {item['snippet']['title']}")
                print(f"Description: {item['snippet']['description']}")
                print("-" * 20)

    except Exception as e:
        print(f"Xatolik: {e}")

if __name__ == "__main__":
    debug_search()
