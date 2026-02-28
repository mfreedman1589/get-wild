import streamlit as st
import requests
import json
from openai import OpenAI

# ==========================================
# 1. CONFIGURATION & SECRETS
# ==========================================
# Pulling securely from Streamlit Cloud Secrets
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

# Set default location to Fairfax, VA area
DEFAULT_LAT = 38.8462
DEFAULT_LNG = -77.3064

# ==========================================
# 2. HELPER FUNCTIONS (The Engine)
# ==========================================
def fetch_local_places(radius_miles, vibe_keyword):
    """Fetches raw data from Google Places API."""
    radius_meters = int(radius_miles * 1609.34)
    url = "https://places.googleapis.com/v1/places:searchNearby"
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.types"
    }
    
    # Translating our app filters into Google's required types
    data = {
        "includedTypes": ["restaurant", "bar", "cafe", "park", "tourist_attraction"],
        "maxResultCount": 15,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": DEFAULT_LAT, "longitude": DEFAULT_LNG},
                "radius": radius_meters
            }
        }
    }

    # The Real API Call
    response = requests.post(url, headers=headers, json=data)
    return response.json().get('places', [])

def get_ai_recommendations(raw_places, user_filters, mode="top_3"):
    """Sends raw places and user filters to the LLM for curation."""
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    if mode == "get_wild":
        instruction = "Select EXACTLY ONE completely random, but highly-rated option that fits the criteria for a spontaneous adventure."
    else:
        instruction = "Select the absolute BEST 3 options that match the user's filters. Filter out tourist traps."

    system_prompt = f"""
    You are the curation engine for an app called 'Get Wild'.
    {instruction}
    Return the result STRICTLY as a JSON object with a 'recommendations' array containing:
    'name', 'address', 'why_its_perfect' (2-sentence pitch), and 'vibe_check' (3-word summary).
    """

    # The Real AI Call
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"FILTERS: {user_filters}\nPLACES: {json.dumps(raw_places)}"}
        ]
    )
    return json.loads(response.choices[0].message.content)

# ==========================================
# 3. STREAMLIT UI (The Frontend)
# ==========================================
st.set_page_config(page_title="Get Wild", page_icon="🎲", layout="centered")

st.title("🎲 Get Wild")
st.markdown("Skip the endless scrolling. Tell us your vibe, and we'll tell you where to go.")

# --- Filters Section ---
st.subheader("What's the plan?")
col1, col2 = st.columns(2)

with col1:
    group_type = st.selectbox("Who is going?", ["Date", "Family Outing", "Friends", "Solo"])
    vibe = st.radio("Inside or Outside?", ["Doesn't Matter", "Outside", "Inside"])

with col2:
    food_pref = st.selectbox("Sustenance?", ["Full Meal", "Just Drinks/Coffee", "No Food Needed"])
    cost = st.radio("Cost?", ["Any Price", "Free / Cheap", "Willing to Splurge"])

distance = st.slider("How far are you willing to travel? (Miles)", 1, 20, 5)

# Combine filters into a string for the AI
current_filters = f"{group_type}, {vibe}, {food_pref}, {cost}, within {distance} miles."

# --- Action Buttons ---
st.write("---")
btn_col1, btn_col2 = st.columns(2)

with btn_col1:
    top_3_clicked = st.button("🌟 Get Top 3 Recommendations", use_container_width=True)

with btn_col2:
    get_wild_clicked = st.button("🎲 GET WILD (Roulette)", type="primary", use_container_width=True)

# ==========================================
# 4. EXECUTION LOGIC
# ==========================================
if top_3_clicked or get_wild_clicked:
    mode = "get_wild" if get_wild_clicked else "top_3"
    
    if get_wild_clicked:
        st.snow() # Fun animation for the roulette option
    
    with st.spinner("Scouting the best local spots..."):
        try:
            # Step 1: Fetch raw data
            raw_places = fetch_local_places(radius_miles=distance, vibe_keyword=current_filters)
            
            # Step 2: Curate with AI
            results = get_ai_recommendations(raw_places, current_filters, mode=mode)
            
            # Step 3: Display Results
            st.write("### Your Handpicked Spots:" if mode == "top_3" else "### Your Spontaneous Adventure:")
            
            for spot in results.get("recommendations", []):
                with st.container():
                    st.subheader(spot['name'])
                    st.caption(f"📍 {spot['address']} | ✨ **{spot['vibe_check']}**")
                    st.write(spot['why_its_perfect'])
                    st.markdown("[Take me there!](https://maps.google.com/?q=" + spot['name'].replace(" ", "+") + ")")
                    st.write("---")
                    
        except Exception as e:
            st.error(f"Whoops! Something went wrong out in the wild: {e}")