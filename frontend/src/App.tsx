import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Route, Routes } from 'react-router-dom';

import { Layout } from './components/Layout';
import { EmptyState } from './components/ui';
import { About } from './pages/About';
import { ArmsRace } from './pages/ArmsRace';
import { BatchScan } from './pages/BatchScan';
import { Detect } from './pages/Detect';
import { ExtractVerify } from './pages/ExtractVerify';
import { Hide } from './pages/Hide';
import { Home } from './pages/Home';
import { HowItWorks } from './pages/HowItWorks';
import { TamperLab } from './pages/TamperLab';

interface BoundaryState {
  error: Error | null;
}

/** Catches render errors so one broken view never blanks the whole app. */
class ErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Development aid only; no user data is included in render errors.
    if (import.meta.env.DEV) console.error(error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto max-w-xl p-8">
          <EmptyState title="This view hit an unexpected error.">
            <p>{this.state.error.message}</p>
            <button type="button" className="btn-secondary mt-4" onClick={() => this.setState({ error: null })}>
              Try again
            </button>
          </EmptyState>
        </div>
      );
    }
    return this.props.children;
  }
}

export function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="hide" element={<Hide />} />
          <Route path="extract" element={<ExtractVerify />} />
          <Route path="detect" element={<Detect />} />
          <Route path="arms-race" element={<ArmsRace />} />
          <Route path="tamper" element={<TamperLab />} />
          <Route path="batch" element={<BatchScan />} />
          <Route path="how-it-works" element={<HowItWorks />} />
          <Route path="about" element={<About />} />
          <Route path="*" element={<EmptyState title="Page not found" />} />
        </Route>
      </Routes>
    </ErrorBoundary>
  );
}
