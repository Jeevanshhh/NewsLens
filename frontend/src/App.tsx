import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import { useAuth } from "./auth/AuthContext";
import Login from "./pages/Login";
import Register from "./pages/Register";
import ResetPassword from "./pages/ResetPassword";
import Home from "./pages/Home";
import ResultsPage from "./pages/ResultsPage";
import ArticleReader from "./pages/ArticleReader";
import AnalyticsPage from "./pages/AnalyticsPage";
import Profile from "./pages/Profile";
import BookmarksPage from "./pages/BookmarksPage";
import SavedSearchesPage from "./pages/SavedSearchesPage";
import SettingsPage from "./pages/SettingsPage";
import LegalPage from "./pages/LegalPage";
import { LEGAL_NAV } from "./legal/content";

function PublicOnly({ children }: { children: ReactNode }) {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return <div className="center muted">Loading…</div>;
  return isAuthenticated ? <Navigate to="/" replace /> : children;
}

export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <PublicOnly>
            <Login />
          </PublicOnly>
        }
      />
      <Route
        path="/register"
        element={
          <PublicOnly>
            <Register />
          </PublicOnly>
        }
      />
      <Route
        path="/reset-password"
        element={
          <PublicOnly>
            <ResetPassword />
          </PublicOnly>
        }
      />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Home />} />
        <Route path="/results/:searchId" element={<ResultsPage />} />
        <Route path="/articles/:id" element={<ArticleReader />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/bookmarks" element={<BookmarksPage />} />
        <Route path="/saved" element={<SavedSearchesPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      {LEGAL_NAV.map((doc) => (
        <Route key={doc.slug} path={`/${doc.slug}`} element={<LegalPage slug={doc.slug} />} />
      ))}
      <Route path="/legal" element={<Navigate to="/about" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
