import instaloader
import getpass
import os

def create_session():
    print("=== Instagram Sessiya Yaratish ===")
    username = input("Instagram login: ").strip()
    if not username:
        print("Login kiritilmadi!")
        return

    password = getpass.getpass("Instagram parol: ").strip()
    if not password:
        print("Parol kiritilmadi!")
        return

    L = instaloader.Instaloader()
    
    try:
        print(f"Ulanmoqda: {username}...")
        L.login(username, password)
        print("Muvaffaqiyatli kirildi!")
        
        # Save to absolute path to be sure
        session_path = os.path.join(os.getcwd(), f"{username}_session")
        L.save_session_to_file(filename=session_path)
        print(f"Sessiya fayli saqlandi: {session_path}")
        print("Endi veb-interfeysda ushbu logindan foydalanishingiz mumkin.")
        
    except Exception as e:
        print(f"Xatolik yuz berdi: {e}")
        if "checkpoint_required" in str(e):
             print("DIQQAT: Instagram tasdiqlash kodi so'rashi mumkin. Iltimos brauzer orqali kirib tasdiqlang yoki keyinroq urining.")

if __name__ == "__main__":
    create_session()
