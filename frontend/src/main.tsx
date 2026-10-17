import { createRoot } from 'react-dom/client';
import { lazy, Suspense } from 'react';
import LandingPage from './LandingPage';
import './style.css';

// The authenticated application (including the Cognito SDK and API client) is
// loaded only for an explicit live route or the OAuth callback.
const liveRoute = location.pathname === '/live' || location.pathname === '/live/' || location.pathname === '/auth/callback';
const recordedRoute = location.pathname === '/recorded' || location.pathname === '/recorded/';
const LiveApp = liveRoute ? lazy(() => import('./App')) : null;
const RecordedDemoApp = recordedRoute ? lazy(() => import('./RecordedDemoApp')) : null;
createRoot(document.getElementById('root')!).render(LiveApp
  ? <Suspense fallback={<main className="loading" role="status">Opening Live Demo… <a href="/">Back to home</a></main>}><LiveApp/></Suspense>
  : RecordedDemoApp
    ? <Suspense fallback={<main className="loading" role="status">Opening Recorded Demo… <a href="/">Back to home</a></main>}><RecordedDemoApp/></Suspense>
    : <LandingPage/>);
