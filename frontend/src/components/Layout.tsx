import { useState, type FormEvent } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

import Sidebar from "./Sidebar";
import AccountNav from "./AccountNav";
import ProfileMenu from "./ProfileMenu";

const PERSONAL = ["/profile", "/bookmarks", "/saved", "/analytics", "/settings"];

export default function Layout() {
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const [term, setTerm] = useState("");

  const path = location.pathname;
  const isResults = path.startsWith("/results");
  const isPersonal = PERSONAL.some((p) => path.startsWith(p));
  const showSidebar = isResults || isPersonal;

  const submitTopSearch = (e: FormEvent) => {
    e.preventDefault();
    const q = term.trim();
    if (q) navigate(`/?q=${encodeURIComponent(q)}`);
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        {showSidebar && (
          <button className="hamburger" aria-label="Toggle menu" onClick={() => setNavOpen((o) => !o)}>
            ☰
          </button>
        )}
        <Link to="/" className="brand">
          <span className="logo">◐</span> NewsLens
        </Link>

        {showSidebar && (
          <form className="topbar-search" onSubmit={submitTopSearch}>
            <span aria-hidden>🔍</span>
            <input
              value={term}
              placeholder="Search news…"
              onChange={(e) => setTerm(e.target.value)}
              aria-label="Search news"
            />
            <button className="go" type="submit" aria-label="Search">→</button>
          </form>
        )}

        <div className="topbar-spacer" />
        <Link to="/bookmarks" className="icon-btn" aria-label="Bookmarks" title="Bookmarks">
          🔖
        </Link>
        <ProfileMenu />
      </header>

      <div className={`body-grid${showSidebar ? "" : " no-sidebar"}`}>
        {isResults && <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />}
        {isPersonal && <AccountNav open={navOpen} onClose={() => setNavOpen(false)} />}
        {navOpen && showSidebar && <div className="scrim" onClick={() => setNavOpen(false)} />}
        <main className="main" key={path}>
          <Outlet />
        </main>
      </div>

      <MobileNav />
    </div>
  );
}

function MobileNav() {
  const location = useLocation();
  const navigate = useNavigate();
  const path = location.pathname;
  const active = (p: string) =>
    p === "/" ? path === "/" : path.startsWith(p);

  const item = (p: string, ico: string, label: string) => (
    <button
      className={`mobile-nav-item${active(p) ? " active" : ""}`}
      onClick={() => navigate(p)}
    >
      <span className="ico">{ico}</span>
      {label}
    </button>
  );

  return (
    <nav className="mobile-nav">
      {item("/", "🏠", "Home")}
      {item("/results", "🔍", "Search")}
      {item("/saved", "🔖", "Saved")}
      {item("/profile", "👤", "Profile")}
    </nav>
  );
}
