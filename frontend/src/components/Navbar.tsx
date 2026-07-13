import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function Navbar() {
  const { user, isManager, isRequester, logout } = useAuth();
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
          <NavLink to="/register-data" className="nav-link">
            Register Data
          </NavLink>
        </>
      ) : isRequester ? (
        <>
          <NavLink to="/requester" className="nav-link">
            My Projects
          </NavLink>
          <NavLink to="/register-data" className="nav-link">
            Register Data
          </NavLink>
        </>
      ) : (
        <NavLink to="/annotator" className="nav-link">
          My Tasks
        </NavLink>
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
