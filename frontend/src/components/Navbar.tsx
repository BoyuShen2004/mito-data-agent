import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function Navbar() {
  const { user, isManager, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <nav className="navbar">
      <span className="brand">🧬 Mito Data Agent</span>
      {isManager ? (
        <>
          <NavLink to="/manager" className="nav-link">
            Dashboard
          </NavLink>
          <NavLink to="/projects" className="nav-link">
            Projects
          </NavLink>
          <NavLink to="/payments" className="nav-link">
            Payments
          </NavLink>
        </>
      ) : (
        <>
          <NavLink to="/annotator" className="nav-link">
            My Tasks
          </NavLink>
          <NavLink to="/my-payments" className="nav-link">
            My Payments
          </NavLink>
        </>
      )}
      <span className="spacer" />
      <span className="muted">
        {user?.username} ({user?.role})
      </span>
      <button className="secondary" onClick={onLogout}>
        Log out
      </button>
    </nav>
  );
}
