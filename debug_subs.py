from googleapiclient.discovery import build
import os

API_KEY_FILE = "youtube_api_key.txt"
USER_CHANNEL_ID = "UCq-w3Mc0Jm7mf_EcWJSV-DA" # @Tarmoq_himoyasi

def debug_subs():
    if not os.path.exists(API_KEY_FILE):
        print("API Key fayli yo'q")
        return

    with open(API_KEY_FILE, "r") as f:
        api_key = f.read().strip()

    youtube = build("youtube", "v3", developerKey=api_key)
    
    print(f"--- OBUNALARNI TEKSHIRISH: {USER_CHANNEL_ID} ---")
    
    try:
        # Check if we can see subscriptions
        response = youtube.subscriptions().list(
            channelId=USER_CHANNEL_ID,
            part="snippet",
            maxResults=50
        ).execute()
        
        items = response.get("items", [])
        if not items:
            print("Obunalar ro'yxati bo'sh yoki ko'rinmayapti.")
        else:
            print(f"Topildi {len(items)} ta obuna:")
            for item in items:
                title = item["snippet"]["title"]
                print(f"- {title}")

    except Exception as e:
        print(f"Xatolik: {e}")
        if "subscriptionForbidden" in str(e) or "requesterPermissions" in str(e):
            print("\nXULOSA: Sizning obunalaringiz maxfiy (PRIVATE).")

if __name__ == "__main__":
    debug_subs()
