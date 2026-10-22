import { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import AppShell from './components/AppShell';
import ErrorBoundary from './components/ErrorBoundary';
import { ToastProvider } from './components/toast';
import { ConfirmProvider, Spinner } from './components/ui';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const GameDetail = lazy(() => import('./pages/GameDetail'));
const AddGame = lazy(() => import('./pages/AddGame'));
const Settings = lazy(() => import('./pages/Settings'));
const NotFound = lazy(() => import('./pages/NotFound'));

function PageFallback() {
  return (
    <div className="flex items-center justify-center gap-2 py-24 text-sm text-muted">
      <Spinner size={16} className="text-accent" />
      加载中…
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <ConfirmProvider>
          <ErrorBoundary>
            <Suspense fallback={<PageFallback />}>
              <Routes>
                <Route element={<AppShell />}>
                  <Route index element={<Dashboard />} />
                  <Route path="/games/:appid" element={<GameDetail />} />
                  <Route path="/add" element={<AddGame />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="*" element={<NotFound />} />
                </Route>
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </ConfirmProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
