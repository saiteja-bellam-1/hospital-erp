import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/badge';
import { useToast } from '../../hooks/use-toast';
import axios from 'axios';
import {
  DownloadCloud, RefreshCw, CheckCircle2, AlertTriangle, Loader2,
  Upload, Rocket, ShieldCheck,
} from 'lucide-react';

const fmtBytes = (n) => {
  const b = Number(n) || 0;
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1)} MB`;
};

const SoftwareUpdate = () => {
  const { toast } = useToast();
  const [info, setInfo] = useState(null);        // /update/check result
  const [checking, setChecking] = useState(false);
  const [status, setStatus] = useState(null);     // /update/status result
  const [applying, setApplying] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  // Offline path
  const [offInstaller, setOffInstaller] = useState(null);
  const [offManifest, setOffManifest] = useState(null);
  const [offBusy, setOffBusy] = useState(false);
  const installerRef = useRef(null);
  const manifestRef = useRef(null);

  const pollRef = useRef(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get('/api/system/update/status');
      setStatus(res.data);
      return res.data;
    } catch {
      return null;
    }
  }, []);

  const runCheck = useCallback(async () => {
    setChecking(true);
    try {
      const res = await axios.get('/api/system/update/check');
      setInfo(res.data);
    } catch (err) {
      const d = err.response?.data?.detail;
      toast({
        variant: 'destructive', title: 'Update check failed',
        description: typeof d === 'string' ? d : 'Could not check for updates',
      });
    } finally {
      setChecking(false);
    }
  }, [toast]);

  // Auto-check + pick up any in-progress download on mount.
  useEffect(() => {
    runCheck();
    fetchStatus();
  }, [runCheck, fetchStatus]);

  // Poll status while a download/verify is in flight.
  useEffect(() => {
    const active = status && (status.state === 'downloading' || status.state === 'verifying');
    if (active && !pollRef.current) {
      pollRef.current = setInterval(fetchStatus, 1500);
    } else if (!active && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [status, fetchStatus]);

  const startDownload = async () => {
    try {
      const res = await axios.post('/api/system/update/download');
      if (!res.data?.started) {
        toast({ variant: 'destructive', title: 'Cannot download',
                description: res.data?.reason || 'Download did not start' });
        return;
      }
      setStatus({ state: 'downloading', bytes: 0, total: 0 });
      fetchStatus();
    } catch (err) {
      const d = err.response?.data?.detail;
      toast({ variant: 'destructive', title: 'Download failed',
              description: typeof d === 'string' ? d : 'Could not start download' });
    }
  };

  const applyUpdate = async () => {
    setConfirmOpen(false);
    setApplying(true);
    try {
      await axios.post('/api/system/update/apply');
      // Backend exits ~2s later — the app will restart. Connection drops here.
    } catch (err) {
      const d = err.response?.data?.detail;
      setApplying(false);
      toast({ variant: 'destructive', title: 'Update could not be applied',
              description: typeof d === 'string' ? d : 'Failed to apply update' });
    }
  };

  const submitOffline = async () => {
    if (!offInstaller || !offManifest) {
      toast({ variant: 'destructive', title: 'Both files required',
              description: 'Select the installer .exe and the manifest.json' });
      return;
    }
    setOffBusy(true);
    try {
      const fd = new FormData();
      fd.append('installer', offInstaller);
      fd.append('manifest', offManifest);
      const res = await axios.post('/api/system/update/upload', fd,
        { headers: { 'Content-Type': 'multipart/form-data' } });
      toast({ title: 'Update staged',
              description: `Version ${res.data?.version} verified and ready to install.` });
      setOffInstaller(null); setOffManifest(null);
      if (installerRef.current) installerRef.current.value = '';
      if (manifestRef.current) manifestRef.current.value = '';
      fetchStatus();
    } catch (err) {
      const d = err.response?.data?.detail;
      toast({ variant: 'destructive', title: 'Upload rejected',
              description: typeof d === 'string' ? d : 'Could not stage the update' });
    } finally {
      setOffBusy(false);
    }
  };

  const st = status?.state || 'idle';
  const isReady = st === 'ready';
  const isDownloading = st === 'downloading' || st === 'verifying';
  const pct = status?.total > 0 ? Math.min(100, Math.round((status.bytes / status.total) * 100)) : 0;

  if (applying) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <Card>
          <CardContent className="py-12 text-center space-y-3">
            <Loader2 className="h-10 w-10 mx-auto animate-spin text-blue-600" />
            <h2 className="text-lg font-semibold">Installing update…</h2>
            <p className="text-sm text-gray-600">
              The application will close and restart automatically. This page will
              lose its connection — wait about a minute, then reload it.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Software Update</h1>
        <p className="text-sm text-gray-500">
          Keep KT HEALTH ERP up to date. Updates are signed and verified before install.
        </p>
      </div>

      {/* Current version + check */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="h-5 w-5 text-blue-600" /> Installed version
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-sm">
              Current version:{' '}
              <span className="font-mono font-semibold">{info?.current_version || '—'}</span>
            </div>
            <Button variant="outline" size="sm" onClick={runCheck} disabled={checking}>
              {checking ? <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                        : <RefreshCw className="h-4 w-4 mr-1" />}
              Check for updates
            </Button>
          </div>

          {info?.error && (
            <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded p-2 text-xs text-amber-900">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{info.error}</span>
            </div>
          )}

          {info && !info.error && !info.update_available && (
            <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded p-2 text-xs text-green-900">
              <CheckCircle2 className="h-4 w-4" />
              You are on the latest version.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Update available */}
      {info?.update_available && (
        <Card className="border-blue-300">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <DownloadCloud className="h-5 w-5 text-blue-600" />
              Update available — v{info.latest_version}
              {info.mandatory && <Badge variant="destructive" className="ml-1">Required</Badge>}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {info.released_at && (
              <p className="text-xs text-gray-500">Released {info.released_at}</p>
            )}
            {info.release_notes && (
              <div className="bg-gray-50 border rounded p-3 text-xs whitespace-pre-wrap max-h-52 overflow-y-auto">
                {info.release_notes}
              </div>
            )}

            {isDownloading && (
              <div className="space-y-1">
                <div className="h-2 bg-gray-200 rounded overflow-hidden">
                  <div className="h-full bg-blue-600 transition-all" style={{ width: `${pct}%` }} />
                </div>
                <p className="text-xs text-gray-500">
                  {st === 'verifying'
                    ? 'Verifying download…'
                    : `Downloading… ${fmtBytes(status?.bytes)}${status?.total ? ' / ' + fmtBytes(status.total) : ''} (${pct}%)`}
                </p>
              </div>
            )}

            {st === 'error' && (
              <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded p-2 text-xs text-red-800">
                <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{status?.error || 'Download failed'}</span>
              </div>
            )}

            {isReady ? (
              <div className="flex items-center gap-2">
                <div className="flex-1 flex items-center gap-2 text-xs text-green-800">
                  <CheckCircle2 className="h-4 w-4" /> Verified and ready to install.
                </div>
                <Button onClick={() => setConfirmOpen(true)}>
                  <Rocket className="h-4 w-4 mr-1" /> Install &amp; Restart
                </Button>
              </div>
            ) : (
              <Button onClick={startDownload} disabled={isDownloading}>
                {isDownloading ? <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                               : <DownloadCloud className="h-4 w-4 mr-1" />}
                Download &amp; Install
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {/* Confirm dialog (inline) */}
      {confirmOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <Card className="max-w-md mx-4">
            <CardHeader>
              <CardTitle className="text-base">Install update now?</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <p>
                The application will close, the update will install, and it will
                restart automatically. You will see one Windows permission
                prompt — approve it to continue.
              </p>
              <p className="text-amber-800 bg-amber-50 border border-amber-200 rounded p-2 text-xs">
                Make sure no one is mid-entry (billing, admissions). The
                database is backed up automatically before the update.
              </p>
              <div className="flex justify-end gap-2 pt-1">
                <Button variant="outline" onClick={() => setConfirmOpen(false)}>Cancel</Button>
                <Button onClick={applyUpdate}>
                  <Rocket className="h-4 w-4 mr-1" /> Install &amp; Restart
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Offline update */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Upload className="h-5 w-5 text-gray-600" /> Offline update
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-gray-500">
            No internet on this machine? Get the installer and its
            <span className="font-mono"> manifest.json</span> from KT Health Soft,
            then upload both here. They are signature-verified before install.
          </p>
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium">Installer (.exe)</label>
              <input ref={installerRef} type="file" accept=".exe"
                     onChange={(e) => setOffInstaller(e.target.files?.[0] || null)}
                     className="block w-full text-xs mt-1" />
            </div>
            <div>
              <label className="text-xs font-medium">Manifest (manifest.json)</label>
              <input ref={manifestRef} type="file" accept=".json,application/json"
                     onChange={(e) => setOffManifest(e.target.files?.[0] || null)}
                     className="block w-full text-xs mt-1" />
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={submitOffline}
                  disabled={offBusy || !offInstaller || !offManifest}>
            {offBusy ? <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                     : <Upload className="h-4 w-4 mr-1" />}
            Verify &amp; stage update
          </Button>
          {isReady && !info?.update_available && (
            <div className="flex items-center gap-2 pt-1">
              <div className="flex-1 flex items-center gap-2 text-xs text-green-800">
                <CheckCircle2 className="h-4 w-4" />
                Update {status?.version} staged and verified.
              </div>
              <Button onClick={() => setConfirmOpen(true)}>
                <Rocket className="h-4 w-4 mr-1" /> Install &amp; Restart
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default SoftwareUpdate;
