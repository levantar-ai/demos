import { Link, NavLink, Route, Routes } from 'react-router-dom';
import Home from './pages/Home.jsx';
import Contact from './pages/Contact.jsx';
import Success from './pages/Success.jsx';
import Admin from './pages/Admin.jsx';

export default function App() {
  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark">▲</span> Northwind
        </Link>
        <nav>
          <NavLink to="/" end>Home</NavLink>
          <NavLink to="/contact">Contact</NavLink>
          <NavLink to="/admin">Submissions</NavLink>
        </nav>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/success" element={<Success />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </main>

      <footer className="footer">
        Demo app · captured by Claude + Playwright · rendered with D3
      </footer>
    </div>
  );
}
