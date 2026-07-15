import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Badge } from '../../../components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../components/ui/select';
import { useToast } from '../../../hooks/use-toast';
import { errorDetail } from '../../../utils/apiErrors';
import {
  ArrowDown, ArrowUp, Loader2, RefreshCw, RotateCcw, Save, Trash2,
} from 'lucide-react';

const STRUCTURAL_TYPES = [
  { type: 'patient_info', label: 'Patient info box' },
  { type: 'consultants', label: 'Consultants' },
  { type: 'medications_table', label: 'Take-home medications table' },
  { type: 'follow_up', label: 'Review / Follow-up' },
  { type: 'condition_on_discharge', label: 'Condition on discharge' },
  { type: 'signatures', label: 'Signature lines' },
  { type: 'acknowledgement', label: 'Acknowledgement' },
];

const DEFAULT_STANDARD_LABELS = {
  chief_complaints_hpi: 'Chief Complaints & History of Present Illness',
  allergies_summary: 'Allergies',
  past_history: 'Past History',
  family_history: 'Family History',
  physical_examination: 'Physical Examination',
  provisional_diagnosis: 'Provisional Diagnosis',
  primary_diagnosis: 'Primary Diagnosis',
  findings_at_admission: 'Key Findings At The Time Of Admission',
  investigations_summary: 'Summary Of Key Investigation',
  course_in_hospital: 'Summary Of Hospital Course',
  procedure_notes: 'Surgery / Procedure Notes',
  discharge_advice: 'Recommendations At Discharge',
};

function newId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `b-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function blockTypeLabel(block) {
  if (block.type === 'standard_section') return `Section: ${block.label || block.field_key}`;
  if (block.type === 'custom_field') return `Custom: ${block.label || block.field_key}`;
  if (block.type === 'static_text') return `Static: ${block.label || 'Note'}`;
  const found = STRUCTURAL_TYPES.find((s) => s.type === block.type);
  return found ? found.label : block.type;
}

const DischargeSummaryTemplatePage = () => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [template, setTemplate] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [addKind, setAddKind] = useState('');
  const [previewUrl, setPreviewUrl] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const blobRef = useRef(null);
  const debounceRef = useRef(null);
  const previewReqId = useRef(0);

  const revokeBlob = useCallback(() => {
    if (blobRef.current) {
      try { URL.revokeObjectURL(blobRef.current); } catch { /* ignore */ }
      blobRef.current = null;
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/inpatient/discharge-summary-template');
      const { standard_field_catalog, ...tpl } = res.data || {};
      setCatalog(standard_field_catalog || Object.keys(DEFAULT_STANDARD_LABELS));
      setTemplate(tpl);
      if (tpl?.blocks?.length) setSelectedId(tpl.blocks[0].id);
    } catch (err) {
      toast({
        title: 'Failed to load template',
        description: errorDetail(err),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => () => {
    revokeBlob();
    if (debounceRef.current) clearTimeout(debounceRef.current);
  }, [revokeBlob]);

  const selected = useMemo(
    () => (template?.blocks || []).find((b) => b.id === selectedId) || null,
    [template, selectedId],
  );

  const usedStandardKeys = useMemo(() => {
    const set = new Set();
    (template?.blocks || []).forEach((b) => {
      if (b.type === 'standard_section' && b.field_key) set.add(b.field_key);
    });
    return set;
  }, [template]);

  const usedStructural = useMemo(() => {
    const set = new Set();
    (template?.blocks || []).forEach((b) => {
      if (STRUCTURAL_TYPES.some((s) => s.type === b.type)) set.add(b.type);
    });
    return set;
  }, [template]);

  const updateBlocks = (nextBlocks) => {
    setTemplate((prev) => ({ ...prev, blocks: nextBlocks }));
  };

  const moveBlock = (id, dir) => {
    const blocks = [...(template?.blocks || [])];
    const idx = blocks.findIndex((b) => b.id === id);
    if (idx < 0) return;
    const j = idx + dir;
    if (j < 0 || j >= blocks.length) return;
    [blocks[idx], blocks[j]] = [blocks[j], blocks[idx]];
    updateBlocks(blocks);
  };

  const removeBlock = (id) => {
    const blocks = (template?.blocks || []).filter((b) => b.id !== id);
    updateBlocks(blocks);
    if (selectedId === id) setSelectedId(blocks[0]?.id || null);
  };

  const patchSelected = (patch) => {
    if (!selected) return;
    updateBlocks(
      (template.blocks || []).map((b) => (b.id === selected.id ? { ...b, ...patch } : b)),
    );
  };

  const handleAdd = (kind) => {
    if (!kind) return;
    let block = null;
    if (kind.startsWith('standard:')) {
      const field_key = kind.slice('standard:'.length);
      block = {
        id: newId(),
        type: 'standard_section',
        field_key,
        label: DEFAULT_STANDARD_LABELS[field_key] || field_key,
        required: field_key === 'primary_diagnosis',
      };
    } else if (kind === 'custom_field') {
      const slug = `custom_${Date.now().toString(36)}`;
      block = {
        id: newId(),
        type: 'custom_field',
        field_key: slug,
        label: 'Custom Field',
        input: 'textarea',
        required: false,
      };
    } else if (kind === 'static_text') {
      block = {
        id: newId(),
        type: 'static_text',
        label: 'Hospital Note',
        content: 'Please bring this summary to your next visit.',
      };
    } else {
      const meta = STRUCTURAL_TYPES.find((s) => s.type === kind);
      if (!meta || usedStructural.has(kind)) return;
      block = { id: newId(), type: kind };
      if (kind === 'consultants') block.label = 'Chief Consultant(s)';
      if (kind === 'medications_table') block.label = 'Take-Home Medications';
      if (kind === 'follow_up') block.label = 'Review / Follow-up';
    }
    const blocks = [...(template?.blocks || []), block];
    updateBlocks(blocks);
    setSelectedId(block.id);
    setAddKind('');
  };

  const handleSave = async () => {
    if (!template) return;
    setSaving(true);
    try {
      const res = await axios.put('/api/inpatient/discharge-summary-template', {
        version: template.version || 1,
        document_title: template.document_title || 'DISCHARGE SUMMARY',
        show_department_line: !!template.show_department_line,
        blocks: template.blocks || [],
      });
      setTemplate(res.data);
      toast({ title: 'Template saved' });
    } catch (err) {
      toast({
        title: 'Save failed',
        description: errorDetail(err),
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!window.confirm('Reset to the default Yashoda-style layout? Your customizations will be removed.')) {
      return;
    }
    setSaving(true);
    try {
      const res = await axios.post('/api/inpatient/discharge-summary-template/reset');
      setTemplate(res.data);
      setSelectedId(res.data?.blocks?.[0]?.id || null);
      toast({ title: 'Template reset to default' });
    } catch (err) {
      toast({
        title: 'Reset failed',
        description: errorDetail(err),
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  const fetchPreview = useCallback(async (tpl) => {
    if (!tpl?.blocks?.length) return;
    const reqId = ++previewReqId.current;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const res = await axios.post(
        '/api/inpatient/discharge-summary-template/preview',
        {
          version: tpl.version || 1,
          document_title: tpl.document_title || 'DISCHARGE SUMMARY',
          show_department_line: !!tpl.show_department_line,
          blocks: tpl.blocks || [],
        },
        { responseType: 'blob' },
      );
      if (reqId !== previewReqId.current) return;
      const contentType = (res.headers['content-type'] || '').toLowerCase();
      if (contentType.includes('application/json')) {
        const text = await res.data.text();
        let detail = 'Failed to generate preview';
        try {
          const parsed = JSON.parse(text);
          detail = typeof parsed.detail === 'string' ? parsed.detail : detail;
        } catch { /* ignore */ }
        throw new Error(detail);
      }
      revokeBlob();
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      blobRef.current = url;
      setPreviewUrl(url);
    } catch (err) {
      if (reqId !== previewReqId.current) return;
      console.error(err);
      let msg = err?.message || errorDetail(err) || 'Failed to generate preview';
      // Axios blob errors often wrap JSON in a Blob
      if (err?.response?.data instanceof Blob) {
        try {
          const text = await err.response.data.text();
          const parsed = JSON.parse(text);
          if (typeof parsed.detail === 'string') msg = parsed.detail;
        } catch { /* ignore */ }
      }
      setPreviewError(msg);
      setPreviewUrl(null);
    } finally {
      if (reqId === previewReqId.current) setPreviewLoading(false);
    }
  }, [revokeBlob]);

  // Live preview: debounce template edits so typing doesn't spam the API
  useEffect(() => {
    if (!template) return undefined;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchPreview(template);
    }, 450);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [template, fetchPreview]);

  if (loading || !template) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading template…
      </div>
    );
  }

  return (
    <div className="p-6 space-y-4 h-full flex flex-col min-h-0">
      <div className="flex flex-wrap items-start justify-between gap-3 shrink-0">
        <div>
          <h2 className="text-lg font-semibold">Discharge Summary Template</h2>
          <p className="text-sm text-gray-500 mt-1">
            Edit blocks on the left — the printed summary updates live on the right.
          </p>
          {template.is_default && (
            <Badge variant="outline" className="mt-2">Using default layout</Badge>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchPreview(template)}
            disabled={previewLoading}
          >
            <RefreshCw className={`h-4 w-4 mr-1 ${previewLoading ? 'animate-spin' : ''}`} />
            Refresh preview
          </Button>
          <Button variant="outline" size="sm" onClick={handleReset} disabled={saving}>
            <RotateCcw className="h-4 w-4 mr-1" /> Reset
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}
            Save
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 border rounded-md p-3 bg-white shrink-0">
        <div className="space-y-1">
          <Label>Document title</Label>
          <Input
            value={template.document_title || ''}
            onChange={(e) => setTemplate({ ...template, document_title: e.target.value })}
          />
        </div>
        <div className="flex items-end gap-2 pb-1">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!template.show_department_line}
              onChange={(e) => setTemplate({
                ...template,
                show_department_line: e.target.checked,
              })}
            />
            Show department line when available
          </label>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 flex-1 min-h-0">
        {/* Left: blocks + selected block settings */}
        <div className="lg:col-span-2 flex flex-col gap-3 min-h-0">
          <div className="border rounded-md bg-white overflow-hidden flex flex-col min-h-0 max-h-[42vh] lg:max-h-none lg:flex-1">
            <div className="px-3 py-2 border-b flex items-center justify-between gap-2 shrink-0">
              <span className="text-sm font-medium">Blocks ({template.blocks?.length || 0})</span>
              <Select value={addKind || undefined} onValueChange={handleAdd}>
                <SelectTrigger className="h-8 w-[160px]">
                  <SelectValue placeholder="Add block…" />
                </SelectTrigger>
                <SelectContent>
                  {catalog.filter((k) => !usedStandardKeys.has(k)).map((k) => (
                    <SelectItem key={k} value={`standard:${k}`}>
                      Section: {DEFAULT_STANDARD_LABELS[k] || k}
                    </SelectItem>
                  ))}
                  <SelectItem value="custom_field">Custom field</SelectItem>
                  <SelectItem value="static_text">Static text</SelectItem>
                  {STRUCTURAL_TYPES.filter((s) => !usedStructural.has(s.type)).map((s) => (
                    <SelectItem key={s.type} value={s.type}>{s.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <ul className="divide-y overflow-y-auto flex-1">
              {(template.blocks || []).map((block, idx) => (
                <li
                  key={block.id}
                  className={`px-2 py-2 flex items-center gap-1 cursor-pointer ${
                    selectedId === block.id ? 'bg-blue-50' : 'hover:bg-gray-50'
                  }`}
                  onClick={() => setSelectedId(block.id)}
                >
                  <span className="text-xs text-gray-400 w-5">{idx + 1}</span>
                  <span className="flex-1 text-sm truncate">{blockTypeLabel(block)}</span>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0"
                    onClick={(e) => { e.stopPropagation(); moveBlock(block.id, -1); }}
                    disabled={idx === 0}
                  >
                    <ArrowUp className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0"
                    onClick={(e) => { e.stopPropagation(); moveBlock(block.id, 1); }}
                    disabled={idx === template.blocks.length - 1}
                  >
                    <ArrowDown className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-7 w-7 p-0"
                    onClick={(e) => { e.stopPropagation(); removeBlock(block.id); }}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-red-500" />
                  </Button>
                </li>
              ))}
            </ul>
          </div>

          <div className="border rounded-md bg-white p-3 space-y-3 shrink-0">
            {!selected ? (
              <p className="text-sm text-gray-500">Select a block to edit its settings.</p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{selected.type}</Badge>
                  <span className="text-sm font-medium">{blockTypeLabel(selected)}</span>
                </div>

                {(selected.type === 'consultants'
                  || selected.type === 'medications_table'
                  || selected.type === 'follow_up'
                  || selected.type === 'standard_section'
                  || selected.type === 'custom_field'
                  || selected.type === 'static_text') && (
                  <div className="space-y-1">
                    <Label>Label</Label>
                    <Input
                      value={selected.label || ''}
                      onChange={(e) => patchSelected({ label: e.target.value })}
                    />
                  </div>
                )}

                {selected.type === 'standard_section' && (
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={!!selected.required}
                      onChange={(e) => patchSelected({ required: e.target.checked })}
                    />
                    Required before finalize
                  </label>
                )}

                {selected.type === 'custom_field' && (
                  <>
                    <div className="space-y-1">
                      <Label>Field key (slug)</Label>
                      <Input
                        value={selected.field_key || ''}
                        onChange={(e) => patchSelected({
                          field_key: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'),
                        })}
                      />
                      <p className="text-xs text-gray-500">Lowercase letters, numbers, underscores.</p>
                    </div>
                    <div className="space-y-1">
                      <Label>Input type</Label>
                      <Select
                        value={selected.input || 'textarea'}
                        onValueChange={(v) => patchSelected({ input: v })}
                      >
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="textarea">Textarea</SelectItem>
                          <SelectItem value="text">Single line</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={!!selected.required}
                        onChange={(e) => patchSelected({ required: e.target.checked })}
                      />
                      Required before finalize
                    </label>
                  </>
                )}

                {selected.type === 'static_text' && (
                  <div className="space-y-1">
                    <Label>Content (always printed)</Label>
                    <Textarea
                      rows={4}
                      value={selected.content || ''}
                      onChange={(e) => patchSelected({ content: e.target.value })}
                    />
                  </div>
                )}

                {(selected.type === 'patient_info'
                  || selected.type === 'condition_on_discharge'
                  || selected.type === 'signatures'
                  || selected.type === 'acknowledgement') && (
                  <p className="text-sm text-gray-500">
                    This structural block has no extra settings. Remove it from the list
                    if your hospital does not want it on the printed summary.
                  </p>
                )}
              </>
            )}
          </div>
        </div>

        {/* Right: live PDF preview */}
        <div className="lg:col-span-3 border rounded-md bg-white overflow-hidden flex flex-col min-h-[420px] lg:min-h-0">
          <div className="px-3 py-2 border-b flex items-center justify-between gap-2 shrink-0 bg-slate-50">
            <span className="text-sm font-medium">Live preview</span>
            {previewLoading && (
              <span className="text-xs text-gray-500 flex items-center gap-1">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> Updating…
              </span>
            )}
          </div>
          <div className="flex-1 min-h-0 relative bg-gray-100">
            {previewError && (
              <div className="absolute inset-0 flex items-center justify-center p-4">
                <p className="text-sm text-red-600 text-center">{previewError}</p>
              </div>
            )}
            {!previewUrl && !previewError && previewLoading && (
              <div className="absolute inset-0 flex items-center justify-center text-gray-500 text-sm">
                <Loader2 className="h-5 w-5 animate-spin mr-2" /> Generating preview…
              </div>
            )}
            {previewUrl && (
              <iframe
                title="Discharge summary preview"
                src={previewUrl}
                className="w-full h-full border-0"
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default DischargeSummaryTemplatePage;
