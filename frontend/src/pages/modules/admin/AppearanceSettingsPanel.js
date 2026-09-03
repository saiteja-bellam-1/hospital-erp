import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import { useToast } from '../../../hooks/use-toast';
import { useAuth } from '../../../contexts/AuthContext';
import { useBranding } from '../../../contexts/BrandingContext';
import { useLayoutPreferences } from '../../../contexts/LayoutPreferencesContext';
import { invalidatePdfPrintSettingsCache } from '../../../hooks/usePdfPrintSettings';
import LabelSettingsFields from '../../../components/LabelSettingsFields';
import { DEFAULT_APP_NAME } from '../../../contexts/BrandingContext';
import { FAVICON_HINT, LOGO_HINT, validateBrandingImageFile } from '../../../utils/brandingImage';
import { Image, PanelLeft, PanelTop, Save, Tag } from 'lucide-react';
import HospitalLogo from '../../../components/HospitalLogo';

const DEFAULT_LAB_LABELS = {
  width_mm: 50, height_mm: 30, labels_per_row: 1, labels_per_column: 1,
  margin_top_mm: 2, margin_left_mm: 2, gutter_mm: 2, sheet_mode: 'thermal',
  sheet_width_mm: 210, sheet_height_mm: 297, show_lab_name: true, lab_name_override: null,
};

const DEFAULT_PHARMACY_LABELS = {
  width_mm: 38, height_mm: 25, labels_per_row: 1, labels_per_column: 1,
  margin_top_mm: 2, margin_left_mm: 2, gutter_mm: 2, sheet_mode: 'thermal',
  sheet_width_mm: 210, sheet_height_mm: 297, show_lab_name: false, lab_name_override: null,
};

function mergeLabelSettings(defaults, raw) {
  if (!raw) return { ...defaults };
  return { ...defaults, ...raw };
}

async function uploadBrandingImage(file, kind) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await axios.post(`/api/hospital/branding/upload?kind=${kind}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data.url;
}

export default function AppearanceSettingsPanel() {
  const { toast } = useToast();
  const { user } = useAuth();
  const { refreshBranding } = useBranding();
  const { navLayout, setNavLayout } = useLayoutPreferences();
  const isSuperAdmin = user?.role === 'super_admin';

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('navigation');
  const [appearanceLayout, setAppearanceLayout] = useState('sidebar');
  const [labLabelSettings, setLabLabelSettings] = useState(DEFAULT_LAB_LABELS);
  const [pharmacyLabelSettings, setPharmacyLabelSettings] = useState(DEFAULT_PHARMACY_LABELS);
  const [brandingForm, setBrandingForm] = useState({
    name: '',
    logo_url: '',
    favicon_url: '',
  });

  useEffect(() => {
    setAppearanceLayout(navLayout === 'header' ? 'header' : 'sidebar');
  }, [navLayout]);

  useEffect(() => {
    const load = async () => {
      try {
        const requests = [axios.get('/api/hospital/print-settings')];
        if (isSuperAdmin) {
          requests.push(axios.get('/api/hospital/branding'));
        }
        const results = await Promise.all(requests);
        const printRes = results[0];
        if (printRes.data.lab_label_settings) {
          setLabLabelSettings(mergeLabelSettings(DEFAULT_LAB_LABELS, printRes.data.lab_label_settings));
        }
        if (printRes.data.pharmacy_label_settings) {
          setPharmacyLabelSettings(mergeLabelSettings(DEFAULT_PHARMACY_LABELS, printRes.data.pharmacy_label_settings));
        }
        if (isSuperAdmin && results[1]) {
          setBrandingForm({
            name: results[1].data.name || '',
            logo_url: results[1].data.logo_url || '',
            favicon_url: results[1].data.favicon_url || '',
          });
        }
      } catch {
        toast({
          variant: 'destructive',
          title: 'Error',
          description: 'Failed to load appearance settings',
        });
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [toast, isSuperAdmin]);

  const handleImageUpload = async (field, event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const kind = field === 'favicon_url' ? 'favicon' : 'logo';
    try {
      await validateBrandingImageFile(file, kind);
      const url = await uploadBrandingImage(file, kind);
      setBrandingForm((prev) => ({ ...prev, [field]: url }));
      toast({ title: kind === 'favicon' ? 'Tab icon uploaded' : 'Logo uploaded' });
    } catch (error) {
      const detail = error?.response?.data?.detail;
      toast({
        variant: 'destructive',
        title: 'Image not allowed',
        description: typeof detail === 'string' ? detail : (error.message || 'Failed to upload image'),
      });
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (activeTab === 'navigation') {
        const res = await axios.put('/api/hospital/ui-settings', {
          nav_layout: appearanceLayout,
        });
        const layout = res.data?.nav_layout === 'header' ? 'header' : 'sidebar';
        setNavLayout(layout);
        setAppearanceLayout(layout);
        toast({
          title: 'Navigation updated',
          description: 'Layout applies to all users on this hospital.',
        });
      } else if (activeTab === 'branding') {
        await axios.put('/api/hospital/branding', brandingForm);
        await refreshBranding();
        toast({
          title: 'Branding saved',
          description: 'App name, logo, and tab icon updated for all users.',
        });
      } else {
        await axios.put('/api/hospital/print-settings', {
          lab_label_settings: labLabelSettings,
          pharmacy_label_settings: pharmacyLabelSettings,
        });
        invalidatePdfPrintSettingsCache();
        toast({
          title: 'Label settings saved',
          description: 'Lab and pharmacy label dimensions updated.',
        });
      }
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: error?.response?.data?.detail || 'Failed to save appearance settings',
      });
    } finally {
      setSaving(false);
    }
  };

  const saveLabel = activeTab === 'navigation'
    ? 'Save navigation'
    : activeTab === 'branding'
      ? 'Save branding'
      : 'Save label settings';

  const tabCount = isSuperAdmin ? 3 : 2;

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading appearance settings…</p>;
  }

  const previewName = brandingForm.name.trim() || DEFAULT_APP_NAME;
  const faviconPreview = brandingForm.favicon_url
    ? `${brandingForm.favicon_url}?v=${Date.now()}`
    : '/favicon.ico';

  return (
    <div className="space-y-4">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className={`grid w-full max-w-2xl grid-cols-${tabCount}`} style={{ gridTemplateColumns: `repeat(${tabCount}, minmax(0, 1fr))` }}>
          <TabsTrigger value="navigation" className="gap-1.5">
            <PanelTop className="h-4 w-4" /> Navigation
          </TabsTrigger>
          {isSuperAdmin && (
            <TabsTrigger value="branding" className="gap-1.5">
              <Image className="h-4 w-4" /> Branding
            </TabsTrigger>
          )}
          <TabsTrigger value="labels" className="gap-1.5">
            <Tag className="h-4 w-4" /> Label printing
          </TabsTrigger>
        </TabsList>

        <TabsContent value="navigation" className="mt-4 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center text-lg">
                <PanelTop className="h-5 w-5 mr-2" />
                Navigation layout
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Applies to all users on this hospital. Changes take effect immediately after save.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-2xl">
                <button
                  type="button"
                  onClick={() => setAppearanceLayout('sidebar')}
                  className={`flex items-start gap-3 rounded-lg border-2 p-4 text-left transition-colors ${
                    appearanceLayout === 'sidebar'
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-muted-foreground/30'
                  }`}
                >
                  <PanelLeft className="h-5 w-5 mt-0.5 shrink-0" />
                  <div>
                    <p className="font-medium">Side menu</p>
                    <p className="text-sm text-muted-foreground mt-0.5">
                      Classic left sidebar with collapsible sections.
                    </p>
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => setAppearanceLayout('header')}
                  className={`flex items-start gap-3 rounded-lg border-2 p-4 text-left transition-colors ${
                    appearanceLayout === 'header'
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-muted-foreground/30'
                  }`}
                >
                  <PanelTop className="h-5 w-5 mt-0.5 shrink-0" />
                  <div>
                    <p className="font-medium">Top menu</p>
                    <p className="text-sm text-muted-foreground mt-0.5">
                      Horizontal header nav with full-width pages and search.
                    </p>
                  </div>
                </button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {isSuperAdmin && (
          <TabsContent value="branding" className="mt-4 space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">App branding</CardTitle>
              </CardHeader>
              <CardContent className="space-y-5 max-w-2xl">
                <p className="text-sm text-muted-foreground">
                  Customise the hospital name, logo, and browser tab icon shown across the app.
                  PDFs and bills continue to use the hospital name from Hospital Info.
                </p>

                <div>
                  <Label htmlFor="branding-name">Hospital / app name</Label>
                  <Input
                    id="branding-name"
                    value={brandingForm.name}
                    onChange={(e) => setBrandingForm({ ...brandingForm, name: e.target.value })}
                    placeholder="Enter hospital name"
                    className="mt-1 max-w-md"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    Used for the browser tab title, login page, navigation logo alt text, and app footer.
                  </p>
                </div>

                <div>
                  <Label>App logo</Label>
                  <div className="mt-1 flex items-center gap-4">
                    {brandingForm.logo_url ? (
                      <HospitalLogo variant="preview" src={brandingForm.logo_url} className="border rounded p-1 bg-white" />
                    ) : (
                      <div className="h-16 w-40 border rounded flex items-center justify-center bg-muted/30 text-xs text-muted-foreground">
                        Default logo
                      </div>
                    )}
                    <div>
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        id="branding-logo-upload"
                        className="hidden"
                        onChange={(e) => handleImageUpload('logo_url', e)}
                      />
                      <Button type="button" variant="outline" size="sm" onClick={() => document.getElementById('branding-logo-upload').click()}>
                        {brandingForm.logo_url ? 'Change logo' : 'Upload logo'}
                      </Button>
                      {brandingForm.logo_url && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="text-red-500 ml-1"
                          onClick={() => setBrandingForm({ ...brandingForm, logo_url: '' })}
                        >
                          Remove
                        </Button>
                      )}
                      <p className="text-[10px] text-gray-400 mt-1">{LOGO_HINT}</p>
                    </div>
                  </div>
                </div>

                <div>
                  <Label>Tab icon (favicon)</Label>
                  <div className="mt-1 flex items-center gap-4">
                    <img
                      src={faviconPreview}
                      alt=""
                      className="h-10 w-10 object-contain border rounded p-1 bg-white"
                      onError={(e) => { e.currentTarget.src = '/favicon.ico'; }}
                    />
                    <div>
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/x-icon,image/vnd.microsoft.icon,.ico"
                        id="branding-favicon-upload"
                        className="hidden"
                        onChange={(e) => handleImageUpload('favicon_url', e)}
                      />
                      <Button type="button" variant="outline" size="sm" onClick={() => document.getElementById('branding-favicon-upload').click()}>
                        {brandingForm.favicon_url ? 'Change icon' : 'Upload icon'}
                      </Button>
                      {brandingForm.favicon_url && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="text-red-500 ml-1"
                          onClick={() => setBrandingForm({ ...brandingForm, favicon_url: '' })}
                        >
                          Remove
                        </Button>
                      )}
                      <p className="text-[10px] text-gray-400 mt-1">{FAVICON_HINT}</p>
                    </div>
                  </div>
                </div>

                <div className="rounded-lg border bg-muted/20 p-4 space-y-3">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Preview</p>
                  <div className="flex items-center gap-2 text-sm">
                    <img src={faviconPreview} alt="" className="h-4 w-4" onError={(e) => { e.currentTarget.src = '/favicon.ico'; }} />
                    <span>{previewName}</span>
                    <span className="text-muted-foreground">— browser tab</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {previewName} — Powered by KT HEALTH ERP
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                    <div className="rounded-md border bg-white p-3">
                      <p className="text-[10px] text-muted-foreground mb-2">Login</p>
                      <div className="flex justify-center">
                        <HospitalLogo variant="login" src={brandingForm.logo_url || undefined} />
                      </div>
                    </div>
                    <div className="rounded-md border p-3" style={{ background: 'hsl(218 40% 13%)' }}>
                      <p className="text-[10px] text-white/50 mb-2">Menu</p>
                      <HospitalLogo variant="sidebar" src={brandingForm.logo_url || undefined} />
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        )}

        <TabsContent value="labels" className="mt-4 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Thermal &amp; Avery labels</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Configure dimensions for lab sample tube labels and pharmacy batch stickers.
                Match the preset to your physical roll — 2-column rolls need labels/row = 2.
              </p>
              <LabelSettingsFields
                title="Lab sample labels"
                settings={labLabelSettings}
                onChange={setLabLabelSettings}
                showLabName
              />
              <LabelSettingsFields
                title="Pharmacy batch labels"
                settings={pharmacyLabelSettings}
                onChange={setPharmacyLabelSettings}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <div className="flex items-center gap-3">
        <Button type="button" onClick={handleSave} disabled={saving}>
          <Save className="h-4 w-4 mr-2" />
          {saving ? 'Saving…' : saveLabel}
        </Button>
        {activeTab === 'navigation' && appearanceLayout === navLayout && (
          <span className="text-xs text-muted-foreground">No navigation changes to save.</span>
        )}
      </div>
    </div>
  );
}
