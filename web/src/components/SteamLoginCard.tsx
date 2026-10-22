import { useCallback, useEffect, useRef, useState } from 'react';
import QRCode from 'qrcode';
import { Link2Off, Loader2, QrCode, ShieldCheck, UserRound } from 'lucide-react';
import { steamApi } from '../lib/api';
import type { QrStart, QrStatus, SteamSession } from '../lib/types';
import { formatDateTime } from '../lib/format';
import { useFetch } from '../hooks/useFetch';
import { Badge, Button, Card, Field, Modal, SectionHeader, Skeleton, useConfirm } from '../components/ui';
import { useToast } from '../components/toast';

const STATUS_TEXT: Record<string, string> = {
  pending: '等待扫码…',
  scanned: '已扫码，请在 Steam 手机 App 中点「确认登录」',
  success: '登录成功',
  expired: '二维码已过期',
};

export default function SteamLoginCard() {
  const toast = useToast();
  const confirm = useConfirm();
  const load = useCallback(() => steamApi.getSession(), []);
  const { data, error, loading, reload } = useFetch<SteamSession>(load, []);

  const [starting, setStarting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [qr, setQr] = useState<QrStart | null>(null);
  const [qrImage, setQrImage] = useState('');
  const [status, setStatus] = useState<QrStatus | null>(null);
  const timer = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (timer.current !== null) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const closeModal = useCallback(() => {
    stopPolling();
    setQr(null);
    setQrImage('');
    setStatus(null);
  }, [stopPolling]);

  const finish = useCallback(
    (result: QrStatus) => {
      setStatus(result);
      if (result.status === 'success') {
        stopPolling();
        toast.success('Steam 账号已连接，现在可以导入私密心愿单了');
        void reload();
        window.setTimeout(closeModal, 1200);
      } else if (result.status === 'expired') {
        stopPolling();
      }
    },
    [closeModal, reload, stopPolling, toast],
  );

  const startPolling = useCallback(
    (session: QrStart) => {
      stopPolling();
      const interval = Math.max(2, session.interval || 5) * 1000;
      timer.current = window.setInterval(() => {
        void steamApi
          .pollQr(session.session_id)
          .then(finish)
          .catch((err: unknown) => {
            stopPolling();
            toast.error(err instanceof Error ? err.message : '二维码状态查询失败');
          });
      }, interval);
    },
    [finish, stopPolling, toast],
  );

  const connect = async () => {
    setStarting(true);
    try {
      const session = await steamApi.startQr();
      setQr(session);
      setStatus({ status: 'pending', account_name: null, steamid: null, message: null });
      setQrImage(
        await QRCode.toDataURL(session.challenge_url, {
          margin: 1,
          width: 240,
          color: { dark: '#0b1520', light: '#ffffff' },
        }),
      );
      startPolling(session);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '生成登录二维码失败');
    } finally {
      setStarting(false);
    }
  };

  const disconnect = async () => {
    const ok = await confirm({
      title: '断开 Steam 账号',
      message: '断开后只能导入公开心愿单，已导入的关注游戏不受影响。',
      confirmText: '断开',
      danger: true,
    });
    if (!ok) return;
    setDisconnecting(true);
    try {
      await steamApi.disconnect();
      toast.success('已断开 Steam 账号');
      await reload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '断开失败');
    } finally {
      setDisconnecting(false);
    }
  };

  const connected = data?.connected === true;
  const statusText = status ? STATUS_TEXT[status.status] ?? status.message ?? status.status : '';

  return (
    <Card className="p-4 sm:p-5">
      <SectionHeader
        title="Steam 账号"
        description="扫码登录后可导入私密心愿单，登录状态仅保存在本机数据库"
        actions={
          connected ? (
            <Button
              size="sm"
              variant="ghost"
              icon={<Link2Off size={14} />}
              loading={disconnecting}
              onClick={() => void disconnect()}
            >
              断开
            </Button>
          ) : (
            <Button size="sm" variant="primary" icon={<QrCode size={14} />} loading={starting} onClick={() => void connect()}>
              扫码登录
            </Button>
          )
        }
      />

      {error ? (
        <p className="text-xs text-bad">读取登录状态失败：{error}</p>
      ) : loading && !data ? (
        <Skeleton className="h-16 w-full" />
      ) : connected ? (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-good/30 bg-good/5 px-3 py-2.5 text-xs">
          <ShieldCheck size={16} className="text-good" />
          <span className="text-ink">{data?.account_name || 'Steam 账号'}</span>
          <span className="num text-dim">SteamID {data?.steamid || '—'}</span>
          {data?.connected_at ? <span className="text-dim">连接于 {formatDateTime(data.connected_at)}</span> : null}
          <Badge tone="good">已连接</Badge>
        </div>
      ) : (
        <div className="flex items-start gap-2 rounded-lg border border-line bg-panel-2 px-3 py-2.5 text-xs text-muted">
          <UserRound size={15} className="mt-0.5 shrink-0 text-accent" />
          <div className="space-y-1">
            <p>未连接 Steam 账号：只能导入「个人资料与心愿单均为公开」的心愿单。</p>
            <p className="text-[11px] text-dim">
              点击右上角「扫码登录」，用 Steam 手机 App 扫码并确认，即可读取自己的私密心愿单。
            </p>
          </div>
        </div>
      )}

      <Modal
        open={qr !== null}
        onClose={closeModal}
        title="扫码登录 Steam"
        description="打开 Steam 手机 App → 扫一扫 → 确认登录"
        size="sm"
      >
        <div className="flex flex-col items-center gap-3">
          {qrImage ? (
            <img
              src={qrImage}
              alt="Steam 登录二维码"
              className="h-60 w-60 rounded-lg bg-white p-2 shadow-[0_0_0_1px_rgba(26,159,255,0.35)]"
            />
          ) : (
            <div className="flex h-60 w-60 items-center justify-center rounded-lg border border-line bg-panel-2">
              <Loader2 size={22} className="animate-spin text-accent" />
            </div>
          )}
          <p className="flex items-center gap-1.5 text-center text-xs text-muted">
            {status?.status === 'success' ? <ShieldCheck size={14} className="text-good" /> : null}
            {statusText}
          </p>
          {status?.account_name ? <p className="text-xs text-ink">账号：{status.account_name}</p> : null}
          {status?.status === 'expired' ? (
            <Button size="sm" variant="secondary" onClick={() => void connect()}>
              重新生成二维码
            </Button>
          ) : (
            <Field label="二维码内容">
              <code className="block max-w-full truncate text-[11px] text-dim">{qr?.challenge_url}</code>
            </Field>
          )}
        </div>
      </Modal>
    </Card>
  );
}
