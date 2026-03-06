# Get Wild — Project Context

## Stack
- Frontend: Streamlit (get-wild.streamlit.app)
- Backend/Auth: Supabase
- AI: OpenAI GPT-4o-mini
- APIs: Google Places, Ticketmaster, OpenWeather, Google Geocoding, Google Timezone
- Repo: github.com/mfreedman1589/get-wild

## Current App Structure
4 tabs: 🔍 Explore | 📍 Saved | 🏆 Rewards | 👤 Profile

### Explore Tab
- Location input + GPS button
- Filters: When / Time / Who / Setting / Food / Budget (all st.segmented_control pills)
- Distance slider
- "🔍 Add specific keyword" toggle button (session state, no expander)
- GET WILD button (1 result, glowing green card) + Top 3 Recommendations button
- Full-screen loading overlay on search (dark green, pulsing 🌿)
- "💡 Here's a Wild Idea" banner (cached per session, excludes saved spots)

### Saved Tab
- Adventure Ledger — saved spots with star ratings
- Rating nudge: spots with notes="chosen", no rating, saved 12hr+ ago surface at top with gold border

### Rewards Tab
- Points Hero: green gradient card (⚡ X Wild Points)
- Recent Activity expander (last 10 points_ledger rows)
- Badges grid: 25 badges, color-coded by category, locked badges in collapsed section
- How to Earn: st.tabs Points + Badges
- Invite Friends: referral link + Text/Email share

### Profile Tab
- One-liner: ⚡ X pts · 🏆 Y badges
- Profile settings form (name, group pref, alcohol, dietary, vibe, accessibility)
- Logout

## Supabase Schema
Tables: user_profiles, saved_spots, recommendation_cache, wild_counter, feedback, points_ledger, badges

### saved_spots key columns
mode (text), group_type (text), setting (text), spend (text), tier_name (text), notes (text), rating (int)

### points_ledger columns
user_id, action_type, points_earned, description, created_at

### badges columns
id, user_id, badge_id, badge_name, badge_emoji, bonus_points, earned_at

### RLS disabled on
feedback, points_ledger, badges

### Key RPC functions
- increment_wild_counter(p_date, p_city)
- increment_user_points(p_user_id, p_points)
- award_referral_points(p_referral_code, p_new_user_id) — SECURITY DEFINER
- get_referral_count(p_referral_code) — SECURITY DEFINER

## Card Design
- Photo (G<!-- TRUNCATED — please complete this section -->
