import os
import datetime
import random
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pymongo import MongoClient
from pydantic import BaseModel
from typing import Optional
from passlib.context import CryptContext

app = FastAPI(title="Kisaan Link Complete Platform")

# Password Hashing Setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------
# DYNAMIC TEMPLATES FOLDER RESOLUTION (Render Compatible)
# -------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

def get_template_response(filename: str):
    file_path = os.path.join(TEMPLATES_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404, 
            detail=f"File '{filename}' was not found in '{TEMPLATES_DIR}'."
        )
    return FileResponse(file_path)

# -------------------------------------------------------------
# DATABASE CONFIGURATION
# -------------------------------------------------------------
FIXED_DB_NAME = "KisaanLink"
DEFAULT_URI = "mongodb+srv://shagilking6669_db_user:tzLBlYOWa4b3wjAg@cluster0.c0l0maa.mongodb.net/?appName=Cluster0"
MONGO_URI = os.getenv("MONGO_URI", DEFAULT_URI)

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client.get_database(FIXED_DB_NAME)
    users_collection = db["users"]
    orders_collection = db["orders"]
    print(f"✅ Connected to Database: '{db.name}'")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")

# -------------------------------------------------------------
# PYDANTIC SCHEMAS
# -------------------------------------------------------------
class UserRegister(BaseModel):
    uid: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    password: str
    role: str
    auth_provider: str

class PasswordLogin(BaseModel):
    identifier: str
    password: str

class ForecastRequest(BaseModel):
    crop: str
    land_acres: float
    region: str

# -------------------------------------------------------------
# ROUTING FOR HTML FILES
# -------------------------------------------------------------
@app.get("/")
async def read_root():
    return get_template_response("index.html")

@app.get("/index.html")
async def read_index():
    return get_template_response("index.html")

@app.get("/forecast.html")
async def read_forecast():
    return get_template_response("forecast.html")

@app.get("/firebase.json")
async def read_firebase_config():
    return get_template_response("firebase.json")

# -------------------------------------------------------------
# AUTHENTICATION & DATA API ENDPOINTS
# -------------------------------------------------------------
@app.post("/api/register")
async def register_user(user: UserRegister):
    try:
        query = {"$or": []}
        if user.phone: query["$or"].append({"phone": user.phone})
        if user.email: query["$or"].append({"email": user.email})
        
        existing_user = await asyncio.to_thread(users_collection.find_one, query) if query["$or"] else None
        if existing_user:
            raise HTTPException(status_code=400, detail="Account with this Phone or Email already exists.")

        # Truncate password to 72 bytes to fully satisfy bcrypt length limitations
        hashed_password = pwd_context.hash(user.password[:72])

        new_user = {
            "uid": user.uid,
            "name": user.name,
            "phone": user.phone,
            "email": user.email,
            "password": hashed_password,
            "role": user.role,
            "auth_provider": user.auth_provider,
            "created_at": datetime.datetime.utcnow()
        }
        await asyncio.to_thread(users_collection.insert_one, new_user)
        return {
            "message": "User registered successfully!", 
            "user": {
                "name": new_user["name"],
                "role": new_user["role"],
                "phone": new_user["phone"],
                "email": new_user["email"]
            }
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database registration failed: {str(e)}")

@app.post("/api/login-password")
async def login_with_password(credentials: PasswordLogin):
    try:
        user = await asyncio.to_thread(
            users_collection.find_one,
            {"$or": [{"phone": credentials.identifier}, {"email": credentials.identifier}]}
        )
        
        if not user or not pwd_context.verify(credentials.password, user.get("password", "")):
            raise HTTPException(status_code=401, detail="Invalid Mobile/Email or Password.")

        return {
            "message": "Login successful",
            "user": {
                "name": user.get("name", "User"),
                "role": user.get("role", "Member"),
                "phone": user.get("phone"),
                "email": user.get("email")
            }
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@app.get("/api/dashboard-stats")
async def get_dashboard_stats():
    try:
        def fetch_stats():
            fpo_count = users_collection.count_documents({"role": "FPO"})
            farmer_count = users_collection.count_documents({"role": "Farmer"})
            order_count = orders_collection.count_documents({})
            
            pipeline = [{"$group": {"_id": None, "totalRevenue": {"$sum": "$amount"}}}]
            revenue_result = list(orders_collection.aggregate(pipeline))
            total_revenue = revenue_result[0]["totalRevenue"] if revenue_result else 0
            return fpo_count, farmer_count, order_count, total_revenue

        fpo_count, farmer_count, order_count, total_revenue = await asyncio.to_thread(fetch_stats)

        return {
            "fpos": fpo_count,
            "farmers": farmer_count,
            "totalOrders": order_count,
            "revenue": total_revenue
        }
    except Exception as e:
        return {
            "fpos": 0,
            "farmers": 0,
            "totalOrders": 0,
            "revenue": 0
        }

@app.post("/api/forecast")
async def generate_forecast(req: ForecastRequest):
    recommended_acres = round(req.land_acres * 0.7, 1)
    return {
        "recommendation": {
            "acres": recommended_acres,
            "plant_date": "Oct 15 - Oct 20" if req.crop == "Potato" else "Immediately",
            "profit_margin": "38.0%" if req.crop == "Potato" else "45.2%",
            "rain_forecast": "Expected in 48 hours"
        },
        "chart_data": {
            "demand": [100 + (i * 2) + random.randint(-5, 5) for i in range(30)],
            "supply": [110 + random.randint(-10, 10) for i in range(30)]
        }
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
