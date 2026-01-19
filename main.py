from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import instaloader
import os
import random
import json
import asyncio
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

app = FastAPI()

# --- CONFIGURATION ---
# CONFIGURATION (Env vars take precedence for Vercel)
MALUMOTLAR_FILE = "malumotlar.txt"
YOUTUBE_TARGETS_FILE = "youtube_targets.txt"
YOUTUBE_API_KEY_FILE = "youtube_api_key.txt"

# INSTAGRAM CREDENTIALS
MASTER_USERNAME = os.getenv("IG_USERNAME", "shamsiddinov_abbos")
MASTER_PASSWORD = os.getenv("IG_PASSWORD", "eA5!Ikml01v9-iX")

# --- MODELS ---
class CheckRequest(BaseModel):
    login: str
    password: str
    safe_mode: bool = True

class YouTubeCheckRequest(BaseModel):
    handle: str

# --- MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def read_root():
    if os.path.exists("index.html"):
        with open("index.html", "r") as f:
            return f.read()
    return "index.html not found"

@app.get("/targets_count")
async def get_targets_count():
    count = 0
    if os.path.exists(MALUMOTLAR_FILE):
        with open(MALUMOTLAR_FILE, "r") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
            count = len(lines)
    return {"count": count}

@app.get("/youtube_targets_count")
async def get_yt_targets_count():
    count = 0
    if os.path.exists(YOUTUBE_TARGETS_FILE):
        with open(YOUTUBE_TARGETS_FILE, "r") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
            count = len(lines)
    return {"count": count}

@app.get("/has_api_key")
async def has_api_key():
    has_key = False
    if os.path.exists(YOUTUBE_API_KEY_FILE):
        with open(YOUTUBE_API_KEY_FILE, "r") as f:
            if f.read().strip():
                has_key = True
    return {"has_key": has_key}

# --- INSTAGRAM LOGIC ---

def get_master_instaloader():
    """
    Returns a logged-in Instaloader instance.
    """
    L = instaloader.Instaloader()
    # User Agent imitation logic can be improved or removed if causing issues, but keeping purely as requested logic
    L.context.user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 15_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 243.1.0.14.111 (iPhone13,3; iOS 15_5; en_US; en-US; scale=3.00; 1170x2532; 382468104)"
    
    session_file = f"{MASTER_USERNAME}_session"
    session_path = os.path.join(os.getcwd(), session_file)
    logged_in = False

    # 1. Try Loading Session
    if os.path.exists(session_path):
        try:
            L.load_session_from_file(MASTER_USERNAME, filename=session_path)
            if L.context.is_logged_in:
                logged_in = True
        except Exception as e:
            print(f"Session load error: {e}")

    # 2. Login if not logged in
    if not logged_in:
        try:
            L.login(MASTER_USERNAME, MASTER_PASSWORD)
            L.save_session_to_file(filename=session_path)
        except Exception as e:
            raise Exception(f"Instagram Login Error: {e}")

    return L

@app.post("/check")
async def check_instagram(request: CheckRequest):
    return StreamingResponse(check_instagram_stream(request), media_type="application/x-ndjson")

async def check_instagram_stream(request: CheckRequest):
    if not request.login:
        yield json.dumps({"error": "Login is required"}) + "\n"
        return

    clean_login = request.login.replace("@", "").strip().lower()
    
    if not os.path.exists(MALUMOTLAR_FILE):
        yield json.dumps({"error": "malumotlar.txt not found"}) + "\n"
        return

    targets = []
    with open(MALUMOTLAR_FILE, "r") as f:
        targets = [line.strip().replace("@", "") for line in f.readlines() if line.strip()]

    try:
        L = get_master_instaloader()
    except Exception as e:
        yield json.dumps({"error": f"Login Error: {str(e)}"}) + "\n"
        return

    target_username = clean_login

    try:
        profile = instaloader.Profile.from_username(L.context, target_username)
        
        if profile.is_private and not profile.followed_by_viewer:
            yield json.dumps({"error": f"@{target_username} is PRIVATE account."}) + "\n"
            return
             
        target_followees = set()
        
        # Retry mechanism for fetching followees
        retries = 1
        for attempt in range(retries + 1):
            try:
                for followee in profile.get_followees():
                    target_followees.add(followee.username)
                break
            except Exception as e:
                if attempt == retries:
                     yield json.dumps({"error": f"Error fetching subscriptions: {e}"}) + "\n"
                     return
                await asyncio.sleep(2)
        
        # Check against targets
        for required_user in targets:
            # Engagement Check Skipped/Disabled by request
            # if request.safe_mode: ... 

            # SKIP ENGAGEMENT CHECK for performance since UI doesn't show it
            is_following = required_user in target_followees
            is_liked = False
            is_commented = False
            like_status = "disabled"
            comment_status = "disabled"
            
            # Artificial Delay REMOVED - In-memory check is safe and fast
            await asyncio.sleep(0.01)

            # try:
            #     req_profile = instaloader.Profile.from_username(L.context, required_user)
            #     ... (Comment/Like logic removed)
            # except Exception:
            #     ...

            data = {
                "target": required_user,
                "is_following": is_following,
                "is_liked": is_liked,
                "is_commented": is_commented,
                "like_status": like_status,
                "comment_status": comment_status,
                "status": "found"
            }
            yield json.dumps(data) + "\n"

    except instaloader.ProfileNotExistsException:
        yield json.dumps({"error": "Instagram profile not found."}) + "\n"
    except Exception as e:
        yield json.dumps({"error": f"Check error: {e}"}) + "\n"


# --- YOUTUBE LOGIC ---

@app.post("/check_youtube")
async def check_youtube(request: YouTubeCheckRequest):
    return StreamingResponse(check_youtube_stream(request), media_type="application/x-ndjson")

async def check_youtube_stream(request: YouTubeCheckRequest):
    # 1. Get API Key (Env Var first, then Request, then File)
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        api_key = request.api_key.strip()
    
    if not api_key and os.path.exists(YOUTUBE_API_KEY_FILE):
        with open(YOUTUBE_API_KEY_FILE, "r") as f:
            api_key = f.read().strip()
            
    if not api_key:
        yield json.dumps({"error": "YouTube API Key topilmadi (Env Var yoki faylda yo'q)"}) + "\n"
        return
    
    if not request.handle or not api_key:
        yield json.dumps({"error": "API Key or Handle missing. Please check youtube_api_key.txt"}) + "\n"
        return

    handle = request.handle.strip()
    
    if not os.path.exists(YOUTUBE_TARGETS_FILE):
        yield json.dumps({"error": "youtube_targets.txt not found"}) + "\n"
        return

    targets = []
    with open(YOUTUBE_TARGETS_FILE, "r") as f:
         targets = [line.strip() for line in f.readlines() if line.strip()]

    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        
        # 1. Resolve User Handle to Channel ID
        yield json.dumps({"status": "info", "message": f"Kanal qidirilmoqda: {handle}..."}) + "\n"
        
        user_channel_id = None
        
        # A. Try Direct Channel ID (if matches pattern)
        if handle.startswith("UC") and len(handle) == 24:
            try:
                ch_resp = youtube.channels().list(id=handle, part="id,snippet").execute()
                if ch_resp.get("items"):
                    user_channel_id = ch_resp["items"][0]["id"]
                    title = ch_resp["items"][0]["snippet"]["title"]
                    yield json.dumps({"status": "info", "message": f"ID orqali topildi: {title}"}) + "\n"
            except HttpError:
                pass

        # B. Try Handle (Best Method)
        if not user_channel_id:
            try:
                # Add '@' if missing for handle search
                handle_query = handle if handle.startswith("@") else f"@{handle}"
                
                ch_resp = youtube.channels().list(
                    forHandle=handle_query, 
                    part="id,snippet"
                ).execute()
                
                if ch_resp.get("items"):
                    user_channel_id = ch_resp["items"][0]["id"]
                    title = ch_resp["items"][0]["snippet"]["title"]
                    yield json.dumps({"status": "info", "message": f"Handle orqali topildi: {title}"}) + "\n"
            except HttpError:
                pass

        # C. Fallback to Search
        if not user_channel_id:
            # Last resort
            try:
                search_response = youtube.search().list(
                    q=handle, part="id,snippet", type="channel", maxResults=1
                ).execute()
                
                if search_response.get("items"):
                    user_channel_id = search_response["items"][0]["id"]["channelId"]
                    title = search_response["items"][0]["snippet"]["title"]
                    yield json.dumps({"status": "info", "message": f"Qidiruv orqali topildi: {title}"}) + "\n"
                else:
                     yield json.dumps({"error": "Bunday YouTube kanal topilmadi. Iltimos, Handle (@user) to'g'ri ekanligiga ishonch hosil qiling."}) + "\n"
                     return
            except HttpError as e:
                yield json.dumps({"error": f"YouTube API Xatosi: {e}"}) + "\n"
                return

        # 2. Check Subscriptions & Comments for each Target
        yield json.dumps({"status": "info", "message": "Checking subscriptions & comments..."}) + "\n"
        
        for target in targets:
            yield json.dumps({"status": "checking", "target": target}) + "\n"
            
            # A. Resolve Target to ID (if not already ID)
            target_id = target
            uploads_playlist_id = None
            
            if not target.startswith("UC") or len(target) != 24:
                try:
                    t_search = youtube.search().list(
                        q=target, part="id", type="channel", maxResults=1
                    ).execute()
                    if t_search.get("items"):
                        target_id = t_search["items"][0]["id"]["channelId"]
                    else:
                        yield json.dumps({"target": target, "status": "not_found_target"}) + "\n"
                        continue
                except:
                     yield json.dumps({"target": target, "status": "error_resolving_target"}) + "\n"
                     continue

            # B. Get Uploads Playlist (for Comment Check)
            try:
                ch_resp = youtube.channels().list(id=target_id, part="contentDetails").execute()
                if ch_resp.get("items"):
                    uploads_playlist_id = ch_resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            except:
                pass

            # C. Check Subscription
            is_following = False
            try:
                check_sub = youtube.subscriptions().list(
                    part="snippet", channelId=user_channel_id, forChannelId=target_id
                ).execute()
                is_following = len(check_sub.get("items", [])) > 0
            except HttpError:
                 pass # Likely private subscriptions or not found
            
            # D. Check Comments (DISABLED)
            is_commented = False
            comment_status = "disabled"
            like_status = "disabled"
            
            # Logic removed for performance as requested
            
            yield json.dumps({
                "target": target,
                "status": "found",
                "is_following": is_following,
                "is_liked": False,
                "is_commented": False,
                "like_status": like_status,
                "comment_status": comment_status
            }) + "\n"
            
            await asyncio.sleep(0.1) # Minimal delay

    except Exception as e:
        yield json.dumps({"error": f"Global Error: {e}"}) + "\n"
