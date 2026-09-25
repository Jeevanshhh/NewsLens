import { useLocation, useNavigate } from "react-router-dom";

// Tab switch shared by the Bookmarks and Saved Searches pages.
export default function LibraryTabs() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const onBookmarks = pathname.startsWith("/bookmarks");

  return (
    <div className="tabs">
      <button
        className={`tab${onBookmarks ? " active" : ""}`}
        onClick={() => navigate("/bookmarks")}
      >
        🔖 Bookmarks
      </button>
      <button
        className={`tab${!onBookmarks ? " active" : ""}`}
        onClick={() => navigate("/saved")}
      >
        🔎 Saved Searches
      </button>
    </div>
  );
}
