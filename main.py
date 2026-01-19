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
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# --- CONFIGURATION ---
# CONFIGURATION (Env vars take precedence for Vercel)
MALUMOTLAR_FILE = "malumotlar.txt"
YOUTUBE_TARGETS_FILE = "youtube_targets.txt"
YOUTUBE_API_KEY_FILE = "youtube_api_key.txt"

# INSTAGRAM CREDENTIALS
MASTER_USERNAME = os.getenv("IG_USERNAME", "shamsiddinov_abbos")
MASTER_PASSWORD = os.getenv("IG_PASSWORD", "eA5!Ikml01v9-iX")

# Executor for blocking synchronous calls
executor = ThreadPoolExecutor(max_workers=5)

# --- MODELS ---
class CheckRequest(BaseModel):
    login: str
    password: str
    safe_mode: bool = True

class YouTubeCheckRequest(BaseModel):
    handle: str
    api_key: str = "" # Added field for optional client-side key

# --- MIDDLEWARE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CACHING UTILS ---
file_cache = {}

def get_cached_lines(filename):
    """Reads lines from a file with mtime caching."""
    if not os.path.exists(filename):
        return []
    
    mtime = os.path.getmtime(filename)
    if filename in file_cache:
        cached_mtime, lines = file_cache[filename]
        if cached_mtime == mtime:
            return lines

    with open(filename, "r") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
        file_cache[filename] = (mtime, lines)
        return lines

# YouTube Channel ID Cache: { "handle_or_name": "UC..." }
yt_channel_cache = {}

# --- ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def read_root():
    if os.path.exists("index.html"):
        with open("index.html", "r") as f:
            return f.read()
    return "index.html not found"

@app.get("/targets_count")
async def get_targets_count():
    lines = get_cached_lines(MALUMOTLAR_FILE)
    return {"count": len(lines)}

@app.get("/youtube_targets_count")
async def get_yt_targets_count():
    lines = get_cached_lines(YOUTUBE_TARGETS_FILE)
    return {"count": len(lines)}

@app.get("/has_api_key")
async def has_api_key():
    has_key = False
    if os.path.exists(YOUTUBE_API_KEY_FILE):
        with open(YOUTUBE_API_KEY_FILE, "r") as f:
            if f.read().strip():
                has_key = True
    return {"has_key": has_key}

# --- INSTAGRAM LOGIC ---

def get_master_instaloader_sync():
    """Blocking Instaloader setup/login."""
    L = instaloader.Instaloader()
    L.context.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    
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

async def get_master_instaloader():
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, get_master_instaloader_sync)

@app.post("/check")
async def check_instagram(request: CheckRequest):
    return StreamingResponse(check_instagram_stream(request), media_type="application/x-ndjson")

async def check_instagram_stream(request: CheckRequest):
    if not request.login:
        yield json.dumps({"error": "Login kiritilishi shart"}) + "\n"
        return

    clean_login = request.login.replace("@", "").strip().lower()
    
    if not os.path.exists(MALUMOTLAR_FILE):
        yield json.dumps({"error": "malumotlar.txt fayli topilmadi"}) + "\n"
        return

    targets = get_cached_lines(MALUMOTLAR_FILE)
    targets = [t.replace("@", "") for t in targets] # Clean targets

    yield json.dumps({"status": "info", "message": "Serverga ulanmoqda..."}) + "\n"
    
    try:
        L = await get_master_instaloader()
    except Exception as e:
        yield json.dumps({"error": f"Login Hatoligi: {str(e)}"}) + "\n"
        return

    target_username = clean_login
    loop = asyncio.get_running_loop()

    try:
        # Non-blocking profile fetch
        def fetch_profile():
            return instaloader.Profile.from_username(L.context, target_username)
        
        profile = await loop.run_in_executor(executor, fetch_profile)
        
        if profile.is_private and not profile.followed_by_viewer:
            yield json.dumps({"error": f"@{target_username} profili YOPIQ (Private)."}) + "\n"
            return
             
        target_followees = set()
        yield json.dumps({"status": "info", "message": "Obunalar ro'yxati yuklanmoqda (Biroz vaqt olishi mumkin)..."}) + "\n"
        
        # Retry mechanism for fetching followees
        retries = 1
        for attempt in range(retries + 1):
            try:
                # We can't fully async iterating an iterator, but we can run the whole loop in executor 
                # OR chunk it. For Instaloader, it's safer to run the whole collection in a thread.
                # However, streaming progress is hard if we run it all in thread. 
                # Compromise: Run the heavyweight `get_followees()` construction and iteration in thread, 
                # but accumulating into a set is fast.
                # Instaloader fetches in pages.
                
                def get_all_followees():
                    fws = set()
                    count = 0
                    for followee in profile.get_followees():
                        fws.add(followee.username)
                        count += 1
                        # We cannot easy yield from executor thread to main async gen.
                    return fws, count

                # Run blocking fetch in thread
                # NOTE: This blocks "Progress updates" until complete. 
                # To bring back progress updates, we'd need a more complex generator wrapper. 
                # For responsiveness, it's better to just wait for it in background than block the event loop.
                # If the user has thousands follows, this might take time.
                
                yield json.dumps({"status": "info", "message": "Obunalar yuklanmoqda (Fondagi jarayon)..."}) + "\n"
                
                target_followees, total_count = await loop.run_in_executor(executor, get_all_followees)
                
                yield json.dumps({"status": "info", "message": f"Yuklandi: {total_count} ta. Tekshirilmoqda..."}) + "\n"
                break
            except Exception as e:
                if attempt == retries:
                     yield json.dumps({"error": f"Error fetching subscriptions: {e}"}) + "\n"
                     return
                await asyncio.sleep(2)
        
        # Check against targets
        # This is CPU bound but fast for small lists.
        batch = []
        for required_user in targets:
            is_following = required_user in target_followees
            data = {
                "target": required_user,
                "is_following": is_following,
                "is_liked": False,
                "is_commented": False,
                "like_status": "disabled",
                "comment_status": "disabled",
                "status": "found"
            }
            batch.append(json.dumps(data) + "\n")
            
            # Flush batch every 10 items to reduce overhead
            if len(batch) >= 10:
                 yield "".join(batch)
                 batch = []
                 await asyncio.sleep(0) # Yield to event loop

        if batch:
            yield "".join(batch)

    except instaloader.ProfileNotExistsException:
        yield json.dumps({"error": "Instagram profil topilmadi."}) + "\n"
    except Exception as e:
        yield json.dumps({"error": f"Tekshirish xatosi: {e}"}) + "\n"


# --- YOUTUBE LOGIC ---

@app.post("/check_youtube")
async def check_youtube(request: YouTubeCheckRequest):
    return StreamingResponse(check_youtube_stream(request), media_type="application/x-ndjson")

async def check_youtube_stream(request: YouTubeCheckRequest):
    # 1. Get API Key
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        api_key = request.api_key.strip()
    
    if not api_key and os.path.exists(YOUTUBE_API_KEY_FILE):
        with open(YOUTUBE_API_KEY_FILE, "r") as f:
            api_key = f.read().strip()
            
    if not api_key:
        yield json.dumps({"error": "YouTube API Key topilmadi (Env Var yoki faylda yo'q)"}) + "\n"
        return
    
    if not request.handle:
        yield json.dumps({"error": "Handle kiritilmadi."}) + "\n"
        return

    handle = request.handle.strip()
    
    if not os.path.exists(YOUTUBE_TARGETS_FILE):
        yield json.dumps({"error": "youtube_targets.txt fayli topilmadi"}) + "\n"
        return

    targets = get_cached_lines(YOUTUBE_TARGETS_FILE)

    try:
        # Create service. Note: build() is technically blocking (http discovery), but usually fast. 
        # We could cache the service object or discovery doc but simpler to thread it if needed.
        # usually it's fine.
        youtube = build("youtube", "v3", developerKey=api_key)
        
        # 1. Resolve User Handle to Channel ID
        yield json.dumps({"status": "info", "message": f"Kanal qidirilmoqda: {handle}..."}) + "\n"
        
        user_channel_id = None
        
        # Check Cache
        if handle in yt_channel_cache:
            user_channel_id = yt_channel_cache[handle]
            yield json.dumps({"status": "info", "message": f"Keshdan topildi: {user_channel_id}"}) + "\n"

        if not user_channel_id:
            # A. Try Direct Channel ID
            if handle.startswith("UC") and len(handle) == 24:
                try:
                    ch_resp = await asyncio.to_thread(youtube.channels().list(id=handle, part="id,snippet").execute)
                    if ch_resp.get("items"):
                        user_channel_id = ch_resp["items"][0]["id"]
                except HttpError:
                    pass

            # B. Try Handle
            if not user_channel_id:
                try:
                    handle_query = handle if handle.startswith("@") else f"@{handle}"
                    ch_resp = await asyncio.to_thread(
                        youtube.channels().list(forHandle=handle_query, part="id,snippet").execute
                    )
                    if ch_resp.get("items"):
                        user_channel_id = ch_resp["items"][0]["id"]
                except HttpError:
                    pass

            # C. Fallback to Search
            if not user_channel_id:
                try:
                    search_response = await asyncio.to_thread(
                        youtube.search().list(q=handle, part="id,snippet", type="channel", maxResults=1).execute
                    )
                    if search_response.get("items"):
                        user_channel_id = search_response["items"][0]["id"]["channelId"]
                    else:
                        yield json.dumps({"error": "Bunday YouTube kanal topilmadi."}) + "\n"
                        return
                except HttpError as e:
                    yield json.dumps({"error": f"YouTube API Xatosi: {e}"}) + "\n"
                    return
            
            # Update Cache
            if user_channel_id:
                 yt_channel_cache[handle] = user_channel_id

        # 2. Check Subscriptions Concurrently
        yield json.dumps({"status": "info", "message": "Obunalar tekshirilmoqda..."}) + "\n"
        
        # Helper function for checking a single target
        async def check_single_target(target):
            target_id = target
            
            # Resolve Target ID if needed
            # (We also cache target IDs implicitly to avoid future lookups? 
            #  Actually, targets list is static mostly, so we can cache it better)
            
            if target in yt_channel_cache:
                target_id = yt_channel_cache[target]
            elif not target.startswith("UC") or len(target) != 24:
                try:
                    t_search = await asyncio.to_thread(
                        youtube.search().list(q=target, part="id", type="channel", maxResults=1).execute
                    )
                    if t_search.get("items"):
                        target_id = t_search["items"][0]["id"]["channelId"]
                        yt_channel_cache[target] = target_id
                    else:
                        return {"target": target, "status": "not_found_target"}
                except:
                     return {"target": target, "status": "error_resolving_target"}
            
            # Check Subscription
            is_following = False
            try:
                check_sub = await asyncio.to_thread(
                    youtube.subscriptions().list(
                        part="snippet", channelId=user_channel_id, forChannelId=target_id
                    ).execute
                )
                is_following = len(check_sub.get("items", [])) > 0
            except HttpError:
                 pass 
            
            return {
                "target": target,
                "status": "found",
                "is_following": is_following,
                "is_liked": False,
                "is_commented": False,
                "like_status": "disabled",
                "comment_status": "disabled"
            }

        # Concurrency Control
        semaphore = asyncio.Semaphore(5) # Max 5 concurrent checks
        async def sem_check(t):
            async with semaphore:
                return await check_single_target(t)

        pending = [sem_check(t) for t in targets]
        
        # Stream results as they complete
        for coro in asyncio.as_completed(pending):
            result = await coro
            yield json.dumps(result) + "\n"

    except Exception as e:
        yield json.dumps({"error": f"Umumiy Xatolik: {e}"}) + "\n"

