import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth";
import Layout, { RequireAuth } from "./components/Layout";
import Fixtures from "./pages/Fixtures";
import Standings from "./pages/Standings";
import MatchPage from "./pages/MatchPage";
import { Login, Register } from "./pages/Auth";
import { BookingDetail, MyBookings } from "./pages/Bookings";
import "./styles.css";

function NotFound() {
  return <p className="empty">Page not found.</p>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/leagues/K1" replace />} />
            <Route path="leagues/:code" element={<Fixtures />} />
            <Route path="leagues/:code/standings" element={<Standings />} />
            <Route path="matches/:id" element={<MatchPage />} />
            <Route path="login" element={<Login />} />
            <Route path="register" element={<Register />} />
            <Route path="bookings" element={<RequireAuth><MyBookings /></RequireAuth>} />
            <Route path="bookings/:reference" element={<RequireAuth><BookingDetail /></RequireAuth>} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
