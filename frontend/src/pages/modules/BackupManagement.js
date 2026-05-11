import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { useToast } from '../../hooks/use-toast';
import axios from 'axios';
import { Badge } from '../../components/ui/badge';
import {
  FolderSync, FolderOpen, Plus, X, Play, CheckCircle2, AlertCircle, Loader2, RefreshCw,
  Database, HardDrive, MapPin, ShieldCheck, Image, FileText, Settings, Clock, Timer, RotateCcw, AlertTriangle, Cloud, Upload
} from 'lucide-react';

const BackupManagement = () => {
  const [loading, setLoading] = useState(true);
  const [systemInfo, setSystemInfo] = useState(null);
  const [locations, setLocations] = useState([]);
  const [newPath, setNewPath] = useState('');
  const [backing, setBacking] = useState(false);
  const [browsing, setBrowsing] = useState(false);
  const [backupResult, setBackupResult] = useState(null);
  const [mirrorStatus, setMirrorStatus] = useState(null);
  const [showMigrateDialog, setShowMigrateDialog] = useState(false);
  const [migratePath, setMigratePath] = useState('');
  const [migrating, setMigrating] = useState(false);
  const [migrateBrowsing, setMigrateBrowsing] = useState(false);
  const [snapshotStatus, setSnapshotStatus] = useState(null);
  const [gdriveStatus, setGdriveStatus] = useState(null);
  const [gdriveBacking, setGdriveBacking] = useState(false);
  const [restorePoints, setRestorePoints] = useState([]);
  const [showRestoreDialog, setShowRestoreDialog] = useState(false);
  const [selectedRestore, setSelectedRestore] = useState(null);
  const [restoring, setRestoring] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [uploadingRestore, setUploadingRestore] = useState(false);
  const { toast } = useToast();

  const fetchSnapshotStatus = async () => {
    try { const res = await axios.get('/api/backup/snapshot-status'); setSnapshotStatus(res.data); } catch {}
  };

  const fetchGdriveStatus = async () => {
    try { const res = await axios.get('/api/backup/gdrive-status'); setGdriveStatus(res.data); } catch {}
  };

  const fetchRestorePoints = async () => {
    try { const res = await axios.get('/api/backup/restore/list'); setRestorePoints(res.data.restore_points || []); } catch {}
  };

  const fetchAll = async () => {
    try {
      const [sysRes, locRes, mirrorRes] = await Promise.all([
        axios.get('/api/backup/system-info'),
        axios.get('/api/backup/locations'),
        axios.get('/api/backup/mirror-status'),
      ]);
      setSystemInfo(sysRes.data);
      setLocations(locRes.data.locations || []);
      setMirrorStatus(mirrorRes.data);
    } catch {} finally {
      setLoading(false);
    }
  };

  const fetchMirrorStatus = async () => {
    try {
      const res = await axios.get('/api/backup/mirror-status');
      setMirrorStatus(res.data);
    } catch {}
  };

  useEffect(() => {
    fetchAll();
    fetchSnapshotStatus();
    fetchRestorePoints();
    fetchGdriveStatus();
    const interval = setInterval(() => { fetchMirrorStatus(); fetchSnapshotStatus(); fetchGdriveStatus(); }, 15000);
    return () => clearInterval(interval);
  }, []);

  const browseFolder = async (callback) => {
    setBrowsing(true);
    try {
      const res = await fetch('/api/backup/browse-folder');
      const data = await res.json();
      if (data.path) callback(data.path);
    } catch {} finally { setBrowsing(false); }
  };

  const saveLocations = async (newLocations) => {
    try {
      const res = await axios.put('/api/backup/locations', { locations: newLocations });
      setLocations(res.data.locations || []);
      if (res.data.errors?.length > 0) {
        toast({ variant: 'destructive', title: 'Some paths invalid', description: res.data.errors.map(e => `${e.path}: ${e.error}`).join('; ') });
      } else {
        toast({ title: 'Saved', description: 'Backup locations updated' });
      }
    } catch { toast({ variant: 'destructive', title: 'Error', description: 'Failed to save locations' }); }
  };

  const addLocation = () => {
    const path = newPath.trim();
    if (path && !locations.includes(path)) {
      saveLocations([...locations, path]);
      setNewPath('');
    }
  };

  const runBackup = async () => {
    setBacking(true); setBackupResult(null);
    try {
      const res = await axios.post('/api/backup/run');
      setBackupResult(res.data);
      const allOk = res.data.results?.every(r => r.success);
      toast({ title: allOk ? 'Backup Complete' : 'Backup Partial', description: allOk ? `Backed up to ${res.data.results.length} location(s)` : 'Some locations failed', variant: allOk ? 'default' : 'destructive' });
    } catch (error) {
      toast({ variant: 'destructive', title: 'Backup Failed', description: error.response?.data?.detail || 'Backup failed' });
    } finally { setBacking(false); }
  };

  const handleMigrate = async () => {
    if (!migratePath.trim()) return;
    setMigrating(true);
    try {
      const res = await axios.post('/api/backup/db-migrate', { new_folder: migratePath.trim() });
      toast({ title: 'Success', description: res.data.message });
      setShowMigrateDialog(false); setMigratePath('');
      fetchAll();
    } catch (error) {
      toast({ variant: 'destructive', title: 'Migration Failed', description: error.response?.data?.detail || 'Failed' });
    } finally { setMigrating(false); }
  };

  const formatDate = (d) => {
    if (!d) return '-';
    try { return new Date(d).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }); }
    catch { return d; }
  };

  if (loading) return <div className="flex items-center justify-center p-12"><Loader2 className="w-6 h-6 animate-spin" /></div>;

  const db = systemInfo?.database;
  const config = systemInfo?.config;
  const uploads = systemInfo?.uploads;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Database & Backup</h1>
        <p className="text-muted-foreground text-sm">Manage your database, backups, and system configuration.</p>
      </div>

      {/* Top Row: Database + Config */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Database Card */}
        {db && (
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Database className="w-4 h-4 text-blue-600" /> Database
                </CardTitle>
                <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => { setMigratePath(''); setShowMigrateDialog(true); }}>
                  <MapPin className="w-3 h-3 mr-1" /> Change Location
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <p className="text-[11px] text-gray-400 uppercase tracking-wider">Location</p>
                <code className="text-xs bg-gray-50 px-2 py-1.5 rounded border block truncate mt-1" title={db.path}>{db.path}</code>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <p className="text-[11px] text-gray-400 uppercase tracking-wider">Size</p>
                  <p className="text-sm font-semibold mt-0.5 flex items-center gap-1"><HardDrive className="w-3.5 h-3.5 text-gray-400" />{db.size_mb} MB</p>
                </div>
                <div>
                  <p className="text-[11px] text-gray-400 uppercase tracking-wider">Integrity</p>
                  <Badge className={`mt-0.5 text-[10px] ${db.integrity === 'ok' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                    <ShieldCheck className="w-3 h-3 mr-0.5" />{db.integrity === 'ok' ? 'Healthy' : db.integrity}
                  </Badge>
                </div>
                <div>
                  <p className="text-[11px] text-gray-400 uppercase tracking-wider">Modified</p>
                  <p className="text-xs text-gray-600 mt-0.5">{formatDate(db.last_modified)}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Config Card */}
        {config && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <Settings className="w-4 h-4 text-gray-600" /> System Configuration
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-[11px] text-gray-400 uppercase tracking-wider">Hospital Name</p>
                  <p className="text-sm font-medium mt-0.5">{config.hospital_name || '-'}</p>
                </div>
                <div>
                  <p className="text-[11px] text-gray-400 uppercase tracking-wider">Setup Complete</p>
                  <Badge className={`mt-0.5 text-[10px] ${config.setup_complete ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700'}`}>
                    {config.setup_complete ? 'Yes' : 'No'}
                  </Badge>
                </div>
              </div>
              <div>
                <p className="text-[11px] text-gray-400 uppercase tracking-wider">Database Path (config)</p>
                <code className="text-xs bg-gray-50 px-2 py-1.5 rounded border block truncate mt-1" title={config.db_path}>{config.db_path || 'Default'}</code>
              </div>
              <div>
                <p className="text-[11px] text-gray-400 uppercase tracking-wider">Backup Locations</p>
                {config.backup_locations?.length > 0 ? (
                  <div className="mt-1 space-y-1">
                    {config.backup_locations.map((loc, i) => (
                      <code key={i} className="text-xs bg-gray-50 px-2 py-1 rounded border block truncate" title={loc}>{loc}</code>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-400 mt-0.5">None configured</p>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Uploads Card */}
      {uploads && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-base">
                <Image className="w-4 h-4 text-purple-600" /> Uploaded Files
              </CardTitle>
              <span className="text-xs text-gray-400">{uploads.files.length} file(s) — {uploads.total_size_kb} KB total</span>
            </div>
          </CardHeader>
          <CardContent>
            {uploads.files.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {uploads.files.map((file, i) => (
                  <div key={i} className="flex items-center gap-3 bg-gray-50 rounded-lg p-3 border">
                    <div className="h-12 w-12 rounded-lg bg-white border flex items-center justify-center overflow-hidden flex-shrink-0">
                      {file.name.match(/\.(png|jpg|jpeg|webp)$/i) ? (
                        <img src={file.url} alt={file.name} className="h-full w-full object-cover" />
                      ) : (
                        <FileText className="w-5 h-5 text-gray-400" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium truncate" title={file.name}>{file.name}</p>
                      <p className="text-[10px] text-gray-400">{file.size_kb} KB</p>
                      {file.used_by && file.used_by.length > 0 ? (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {file.used_by.map((usage, j) => (
                            <span key={j} className="text-[9px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded-full font-medium">{usage}</span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-[9px] text-gray-400 mt-0.5 block">Not in use</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-4">No files uploaded yet</p>
            )}
            <p className="text-[10px] text-gray-400 mt-3">Directory: <code className="bg-gray-50 px-1 rounded">{uploads.directory}</code></p>
          </CardContent>
        </Card>
      )}

      {/* Scheduled Snapshots */}
      {snapshotStatus && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-base">
                <Timer className={`w-4 h-4 ${snapshotStatus.running ? 'text-blue-500' : 'text-gray-400'}`} />
                Scheduled Snapshots
              </CardTitle>
              <Badge className={`text-[10px] ${snapshotStatus.running ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600'}`}>
                {snapshotStatus.running ? 'Active' : 'Stopped'}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-gray-600">
              {snapshotStatus.running
                ? `Taking a DB snapshot every ${snapshotStatus.interval_minutes} minutes. Retaining for ${snapshotStatus.retention_hours} hours.`
                : 'Scheduled snapshots are not running.'}
            </p>

            {/* Config */}
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <Label className="text-xs">Interval</Label>
                <select className="block mt-1 h-9 px-2 border rounded-md text-sm bg-white"
                  value={snapshotStatus.interval_minutes}
                  onChange={async (e) => {
                    const val = parseInt(e.target.value);
                    try {
                      await axios.put('/api/backup/snapshot-config', { interval_minutes: val, retention_hours: snapshotStatus.retention_hours });
                      fetchSnapshotStatus();
                      toast({ title: 'Updated', description: `Interval set to ${val} min` });
                    } catch {}
                  }}>
                  <option value="15">15 min</option>
                  <option value="30">30 min</option>
                  <option value="60">1 hour</option>
                  <option value="120">2 hours</option>
                  <option value="360">6 hours</option>
                </select>
              </div>
              <div>
                <Label className="text-xs">Retention</Label>
                <select className="block mt-1 h-9 px-2 border rounded-md text-sm bg-white"
                  value={snapshotStatus.retention_hours}
                  onChange={async (e) => {
                    const val = parseInt(e.target.value);
                    try {
                      await axios.put('/api/backup/snapshot-config', { interval_minutes: snapshotStatus.interval_minutes, retention_hours: val });
                      fetchSnapshotStatus();
                      toast({ title: 'Updated', description: `Retention set to ${val}h` });
                    } catch {}
                  }}>
                  <option value="24">24 hours</option>
                  <option value="48">48 hours</option>
                  <option value="72">3 days</option>
                  <option value="168">7 days</option>
                  <option value="336">14 days</option>
                  <option value="720">30 days</option>
                </select>
              </div>
              <div className="flex gap-2">
                {snapshotStatus.running ? (
                  <Button size="sm" variant="outline" className="h-9" onClick={async () => {
                    await axios.post('/api/backup/snapshot/stop'); fetchSnapshotStatus();
                    toast({ title: 'Snapshots stopped' });
                  }}>Stop</Button>
                ) : (
                  <Button size="sm" className="h-9" onClick={async () => {
                    await axios.post('/api/backup/snapshot/start'); fetchSnapshotStatus();
                    toast({ title: 'Snapshots started' });
                  }}>Start</Button>
                )}
              </div>
            </div>

            {/* Stats */}
            {snapshotStatus.info && (
              <div className="flex gap-4 text-xs text-gray-500 pt-2 border-t">
                <span>{snapshotStatus.info.total_count} snapshot(s)</span>
                <span>{snapshotStatus.info.total_size_mb} MB total</span>
                {snapshotStatus.last_snapshot && (
                  <span>Last: {formatDate(snapshotStatus.last_snapshot)}</span>
                )}
                {snapshotStatus.last_error && (
                  <span className="text-red-500">Error: {snapshotStatus.last_error}</span>
                )}
              </div>
            )}

            {/* Recent snapshots list */}
            {snapshotStatus.info?.recent?.length > 0 && (
              <div className="max-h-32 overflow-y-auto space-y-1">
                {snapshotStatus.info.recent.map((s, i) => (
                  <div key={i} className="flex items-center justify-between text-xs bg-gray-50 rounded px-2.5 py-1.5 border">
                    <span className="font-mono text-gray-600">{s.filename}</span>
                    <span className="text-gray-400">{s.size_mb} MB — {formatDate(s.created)}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Google Drive Backup */}
      {gdriveStatus?.enabled && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-base">
                <Cloud className={`w-4 h-4 ${gdriveStatus.last_sent === new Date().toISOString().split('T')[0] ? 'text-green-500' : 'text-gray-400'}`} />
                Google Drive Backup
              </CardTitle>
              <Badge className={`text-[10px] ${
                gdriveStatus.last_sent === new Date().toISOString().split('T')[0]
                  ? 'bg-green-100 text-green-700'
                  : gdriveStatus.last_error
                    ? 'bg-red-100 text-red-700'
                    : 'bg-gray-100 text-gray-600'
              }`}>
                {gdriveStatus.last_sent === new Date().toISOString().split('T')[0]
                  ? 'Sent today'
                  : gdriveStatus.last_error ? 'Error' : 'Waiting'}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-gray-600">
              Daily compressed backup uploaded to Google Drive automatically.
            </p>
            <div className="flex gap-4 text-xs text-gray-500">
              {gdriveStatus.last_sent && <span>Last sent: {gdriveStatus.last_sent}</span>}
              {gdriveStatus.last_error && <span className="text-red-500">Error: {gdriveStatus.last_error}</span>}
            </div>
            <Button size="sm" className="h-8" disabled={gdriveBacking} onClick={async () => {
              setGdriveBacking(true);
              try {
                await axios.post('/api/backup/gdrive-backup-now');
                toast({ title: 'Success', description: 'Backed up to Google Drive' });
                fetchGdriveStatus();
              } catch (err) {
                toast({ variant: 'destructive', title: 'Failed', description: err.response?.data?.detail || 'Backup failed' });
              } finally { setGdriveBacking(false); }
            }}>
              {gdriveBacking ? <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> Uploading...</> : <><Cloud className="w-3.5 h-3.5 mr-1.5" /> Backup Now</>}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Mirror Status + Manual Backup Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Mirror Status */}
        {mirrorStatus && (
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-base">
                  <RefreshCw className={`w-4 h-4 ${mirrorStatus.running ? 'animate-spin text-green-500' : 'text-gray-400'}`} />
                  Mirror Backup
                </CardTitle>
                <Badge className={`text-[10px] ${mirrorStatus.running ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
                  {mirrorStatus.running ? 'Active' : 'Stopped'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <p className="text-sm text-gray-600">
                  {mirrorStatus.running ? 'Mirroring every 60 seconds.' : 'Not running. Add backup locations to enable.'}
                </p>
                {mirrorStatus.last_sync && (
                  <p className="text-xs text-gray-400">Last sync: {formatDate(mirrorStatus.last_sync)}</p>
                )}
                {mirrorStatus.last_error && (
                  <p className="text-xs text-red-500">Error: {mirrorStatus.last_error}</p>
                )}
                <div className="flex gap-2 pt-1">
                  {mirrorStatus.running ? (
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={async () => {
                      await axios.post('/api/backup/mirror/stop'); fetchMirrorStatus();
                      toast({ title: 'Mirror stopped' });
                    }}>Stop</Button>
                  ) : (
                    <Button size="sm" className="h-7 text-xs" onClick={async () => {
                      await axios.post('/api/backup/mirror/start'); fetchMirrorStatus();
                      toast({ title: 'Mirror started' });
                    }}>Start</Button>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Run Backup */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Play className="w-4 h-4 text-blue-600" /> Manual Backup
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-gray-600">Creates a timestamped copy in each backup location.</p>
            <Button onClick={runBackup} disabled={backing || locations.length === 0} size="sm">
              {backing ? <><Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> Backing up...</> : <><Play className="w-3.5 h-3.5 mr-1.5" /> Run Backup Now</>}
            </Button>
            {backupResult && (
              <div className="space-y-1.5 mt-2">
                <p className="text-xs font-medium">File: <code className="bg-gray-100 px-1 rounded">{backupResult.backup_file}</code></p>
                {backupResult.results?.map((r, i) => (
                  <div key={i} className={`flex items-center gap-1.5 text-xs p-1.5 rounded ${r.success ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                    {r.success ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}
                    <span className="truncate">{r.message}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Backup Locations */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <FolderSync className="w-4 h-4" /> Backup Locations
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Input value={newPath} onChange={(e) => setNewPath(e.target.value)} placeholder="E:\Backups\KTHEALTHERP or network path"
              onKeyDown={(e) => e.key === 'Enter' && addLocation()} className="h-9" />
            <Button variant="outline" onClick={() => browseFolder(setNewPath)} disabled={browsing} className="h-9">
              <FolderOpen className="w-4 h-4 mr-1" /> {browsing ? '...' : 'Browse'}
            </Button>
            <Button onClick={addLocation} disabled={!newPath.trim()} className="h-9">
              <Plus className="w-4 h-4 mr-1" /> Add
            </Button>
          </div>
          {locations.length > 0 ? (
            <div className="space-y-1.5">
              {locations.map((loc, i) => (
                <div key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2 border">
                  <code className="text-xs truncate">{loc}</code>
                  <button onClick={() => { const updated = locations.filter((_, j) => j !== i); saveLocations(updated); }}
                    className="text-gray-400 hover:text-red-500 ml-2 flex-shrink-0"><X className="w-3.5 h-3.5" /></button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 text-center py-3">No backup locations configured.</p>
          )}
        </CardContent>
      </Card>

      {/* Restore from Backup */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <RotateCcw className="w-4 h-4 text-amber-600" /> Restore Database
            </CardTitle>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" className="h-7 text-xs"
                onClick={() => { setUploadFile(null); setShowUploadDialog(true); }}>
                <Upload className="w-3 h-3 mr-1" /> Upload .db file
              </Button>
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={fetchRestorePoints}>
                <RefreshCw className="w-3 h-3 mr-1" /> Refresh
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-gray-600">Restore your database from a previous backup, or upload a .db backup file from disk. A safety backup is created automatically before restoring.</p>
          {restorePoints.length > 0 ? (
            <div className="max-h-48 overflow-y-auto space-y-1.5">
              {restorePoints.map((rp, i) => (
                <div key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2 border text-xs">
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <Badge className={`text-[9px] shrink-0 ${
                      rp.type === 'manual' ? 'bg-blue-100 text-blue-700' :
                      rp.type === 'snapshot' ? 'bg-purple-100 text-purple-700' :
                      'bg-green-100 text-green-700'
                    }`}>{rp.type}</Badge>
                    <span className="font-mono text-gray-600 truncate">{rp.filename}</span>
                    <span className="text-gray-400 shrink-0">{rp.size_mb} MB</span>
                    <span className="text-gray-400 shrink-0">{formatDate(rp.created)}</span>
                    {rp.has_uploads && <Badge className="text-[8px] bg-gray-200 text-gray-600">+uploads</Badge>}
                  </div>
                  <Button size="sm" variant="ghost" className="h-6 text-[10px] text-amber-600 hover:text-amber-800 hover:bg-amber-50 px-2 shrink-0 ml-2"
                    onClick={() => { setSelectedRestore(rp); setShowRestoreDialog(true); }}>
                    Restore
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 text-center py-3">No backup files found. Run a backup first.</p>
          )}
        </CardContent>
      </Card>

      {/* Restore Confirmation Dialog */}
      <Dialog open={showRestoreDialog} onOpenChange={setShowRestoreDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" /> Confirm Restore
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-800">
              <p className="font-semibold">This will replace ALL current data.</p>
              <p className="mt-1 text-xs">A pre-restore backup will be saved automatically. All users will need to re-login after restore.</p>
            </div>
            {selectedRestore && (
              <div className="bg-gray-50 rounded-lg p-3 space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Source</span>
                  <Badge className={`text-[10px] ${
                    selectedRestore.type === 'manual' ? 'bg-blue-100 text-blue-700' :
                    selectedRestore.type === 'snapshot' ? 'bg-purple-100 text-purple-700' :
                    'bg-green-100 text-green-700'
                  }`}>{selectedRestore.type} backup</Badge>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">File</span>
                  <span className="font-mono text-xs">{selectedRestore.filename}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Date</span>
                  <span>{formatDate(selectedRestore.created)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Size</span>
                  <span>{selectedRestore.size_mb} MB</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Includes uploads</span>
                  <span>{selectedRestore.has_uploads ? 'Yes' : 'No'}</span>
                </div>
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="outline" onClick={() => setShowRestoreDialog(false)}>Cancel</Button>
              <Button variant="destructive" disabled={restoring}
                onClick={async () => {
                  setRestoring(true);
                  try {
                    const res = await axios.post('/api/backup/restore', {
                      backup_path: selectedRestore.path,
                      backup_type: selectedRestore.type,
                    });
                    setShowRestoreDialog(false);
                    alert(`${res.data.message}\n\nPre-restore backup: ${res.data.pre_restore_backup || 'none'}\nUploads restored: ${res.data.uploads_restored ? 'Yes' : 'No'}\n\nYou will be logged out now.`);
                    localStorage.clear();
                    window.location.href = '/';
                  } catch (err) {
                    alert(err.response?.data?.detail || 'Restore failed');
                  } finally { setRestoring(false); }
                }}>
                {restoring ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Restoring...</> : 'Restore Database'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Upload .db Restore Dialog */}
      <Dialog open={showUploadDialog} onOpenChange={(open) => { if (!uploadingRestore) setShowUploadDialog(open); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Upload className="h-5 w-5 text-amber-500" /> Restore from uploaded .db file
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-800">
              <p className="font-semibold">This will replace ALL current data.</p>
              <p className="mt-1 text-xs">A pre-restore backup is saved automatically before the swap. All users will be logged out after restore.</p>
            </div>
            <div className="space-y-2">
              <Label className="text-xs">Backup database file (.db)</Label>
              <Input type="file" accept=".db,application/octet-stream"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)} disabled={uploadingRestore} />
              {uploadFile && (
                <div className="text-xs text-gray-600 bg-gray-50 rounded p-2">
                  <div className="font-mono truncate">{uploadFile.name}</div>
                  <div className="text-gray-400">{(uploadFile.size / (1024 * 1024)).toFixed(2)} MB</div>
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="outline" disabled={uploadingRestore} onClick={() => setShowUploadDialog(false)}>Cancel</Button>
              <Button variant="destructive" disabled={!uploadFile || uploadingRestore}
                onClick={async () => {
                  if (!uploadFile) return;
                  setUploadingRestore(true);
                  try {
                    const fd = new FormData();
                    fd.append('file', uploadFile);
                    const res = await axios.post('/api/backup/restore-upload', fd, {
                      headers: { 'Content-Type': 'multipart/form-data' },
                    });
                    setShowUploadDialog(false);
                    alert(`${res.data.message}\n\nPre-restore backup: ${res.data.pre_restore_backup || 'none'}\nUploads restored: ${res.data.uploads_restored ? 'Yes' : 'No'}\n\nYou will be logged out now.`);
                    localStorage.clear();
                    window.location.href = '/';
                  } catch (err) {
                    const detail = err.response?.data?.detail;
                    alert(typeof detail === 'string' ? detail : 'Restore from upload failed');
                  } finally { setUploadingRestore(false); }
                }}>
                {uploadingRestore ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Uploading & Restoring...</> : 'Upload & Restore'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Migrate Dialog */}
      <Dialog open={showMigrateDialog} onOpenChange={setShowMigrateDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><MapPin className="h-5 w-5" /> Change Database Location</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
              This will copy your database to a new location using a safe backup method. The original file will be kept as a fallback.
            </div>
            {db && (
              <div>
                <p className="text-xs text-gray-500 mb-1">Current Location</p>
                <code className="text-sm bg-gray-50 px-2 py-1 rounded border block truncate">{db.path}</code>
              </div>
            )}
            <div>
              <Label>New Folder</Label>
              <div className="flex gap-2 mt-1">
                <Input value={migratePath} onChange={(e) => setMigratePath(e.target.value)} placeholder="D:\KTHealthData" />
                <Button variant="outline" onClick={async () => {
                  setMigrateBrowsing(true);
                  try { const res = await fetch('/api/backup/browse-folder'); const data = await res.json(); if (data.path) setMigratePath(data.path); } catch {} finally { setMigrateBrowsing(false); }
                }} disabled={migrateBrowsing}>
                  <FolderOpen className="w-4 h-4 mr-1" /> {migrateBrowsing ? '...' : 'Browse'}
                </Button>
              </div>
              <p className="text-xs text-gray-400 mt-1">The file <code className="bg-gray-100 px-0.5 rounded">kthealth_erp.db</code> will be created in this folder.</p>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="outline" onClick={() => setShowMigrateDialog(false)}>Cancel</Button>
              <Button onClick={handleMigrate} disabled={migrating || !migratePath.trim()}>
                {migrating ? <><Loader2 className="w-4 h-4 mr-1 animate-spin" /> Migrating...</> : 'Move Database'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default BackupManagement;
