import React, { Suspense, lazy, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import Landing from './Landing.jsx';
import './styles.css';
import { BrandMark } from './BrandLogo.jsx';
const Dashboard = lazy(() => import('./Dashboard.jsx'));

function App() {
  const [route, setRoute] = useState(window.location.hash);
  useEffect(() => {
    const change = () => { setRoute(window.location.hash); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', change);
    return () => window.removeEventListener('hashchange', change);
  }, []);
  const openApp = () => { window.location.hash = '/app'; };
  const isApp = route.startsWith('#/app');
  return <Suspense fallback={<div className="loading-screen"><BrandMark size={50} className="loading-mark" /><span>ENTERING YOUR WORKSPACE</span></div>}>
    {isApp ? <Dashboard onBack={() => { window.location.hash = ''; }} /> : <Landing onOpenApp={openApp} />}
  </Suspense>;
}

createRoot(document.getElementById('root')).render(<App />);
