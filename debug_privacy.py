from googleapiclient.discovery import build
import os

API_KEY_FILE = "youtube_api_key.txt"

def debug_check_user_privacy():
    if not os.path.exists(API_KEY_FILE):
        print("API Key fayli yo'q")
        return

    with open(API_KEY_FILE, "r") as f:
        api_key = f.read().strip()

    youtube = build("youtube", "v3", developerKey=api_key)
    handle = "@AbduaxatovAbduaxatov"
    
    print(f"--- TEKSHIRUV: {handle} ---")
    
    # 1. Get Channel ID
    try:
        ch_resp = youtube.channels().list(forHandle=handle, part="id,snippet").execute()
        if not ch_resp.get("items"):
             # Try search
             ch_resp = youtube.search().list(q=handle, part="id,snippet", type="channel", maxResults=1).execute()
        
        if not ch_resp.get("items"):
            print("Kanal topilmadi!")
            return
            
        # Handle search vs channels.list response structure difference
        item = ch_resp["items"][0]
        channel_id = item["id"] if isinstance(item["id"], str) else item["id"]["channelId"]
        title = item["snippet"]["title"]
        
        print(f"Kanal: {title} (ID: {channel_id})")
        
        # 2. Check Subscriptions
        try:
            sub_resp = youtube.subscriptions().list(
                channelId=channel_id,
                part="snippet",
                maxResults=5
            ).execute()
            
            print("Obunalar ro'yxati OCHIQ (Public).")
            print(f"Topildi: {len(sub_resp.get('items', []))} ta obuna (misol uchun).")
            for sub in sub_resp.get("items", []):
                print(f"- {sub['snippet']['title']}")
                
        except Exception as e:
            if "subscriptionForbidden" in str(e):
                print("!!! DIAGNOZ: Obunalar YASHIRIN (Private).")
                print("Dastur ishlay olmaydi, chunki obunalar ro'yxati yopiq.")
            else:
                print(f"Boshqa xatolik: {e}")

    except Exception as e:
        print(f"Xatolik: {e}")

if __name__ == "__main__":
    debug_check_user_privacy()
