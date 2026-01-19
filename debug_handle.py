from googleapiclient.discovery import build
import os

API_KEY_FILE = "youtube_api_key.txt"

def debug_handle():
    if not os.path.exists(API_KEY_FILE):
        print("API Key fayli yo'q")
        return

    with open(API_KEY_FILE, "r") as f:
        api_key = f.read().strip()

    youtube = build("youtube", "v3", developerKey=api_key)
    
    # Try multiple variations
    handles = ["@Tarmoq_himoyasi", "Tarmoq_himoyasi", "Dasturchi"]
    
    print("--- HANDLE TEKSHIRUVI (forHandle) ---")
    
    for h in handles:
        print(f"\nTekshirilmoqda: {h}")
        try:
            # Note: forHandle parameter
            response = youtube.channels().list(
                forHandle=h,
                part="id,snippet"
            ).execute()
            
            if response.get("items"):
                print("TOPILDI!")
                print(f"ID: {response['items'][0]['id']}")
                print(f"Title: {response['items'][0]['snippet']['title']}")
            else:
                print("Topilmadi.")
                
        except Exception as e:
            print(f"Xatolik (forHandle): {e}")

if __name__ == "__main__":
    debug_handle()
