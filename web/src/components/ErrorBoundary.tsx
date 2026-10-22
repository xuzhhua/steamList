import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Keeps a rendering bug from blanking out the whole SPA: if a page throws,
 * the shell stays visible and the user gets a readable message.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error('页面渲染失败', error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="mx-auto max-w-lg px-4 py-16 text-center">
        <h2 className="text-base font-semibold text-ink">页面出错了</h2>
        <p className="mt-2 text-xs leading-5 text-muted">
          这个页面渲染时遇到异常，已阻止整个界面白屏。可以重新加载页面重试；如果持续出现，请把下面的信息反馈给维护者。
        </p>
        <pre className="mt-3 overflow-x-auto rounded-lg border border-line bg-panel-2 p-3 text-left text-[11px] leading-5 text-bad">
          {error.message}
        </pre>
        <div className="mt-4 flex justify-center gap-2">
          <button
            type="button"
            className="focus-ring rounded-md border border-line px-3 py-1.5 text-xs text-muted transition hover:border-accent/50 hover:text-accent"
            onClick={() => this.setState({ error: null })}
          >
            重试
          </button>
          <button
            type="button"
            className="focus-ring rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-[#04121b] transition hover:brightness-110"
            onClick={() => window.location.reload()}
          >
            刷新页面
          </button>
        </div>
      </div>
    );
  }
}
