import React from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, Monitor, Headphones, LogOut, LayoutDashboard } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { useBranding } from '../../contexts/BrandingContext';
import { useNavigationSections } from '../../hooks/useNavigationSections';

const APP_COLORS = [
  '#296DAE',
  '#00A09D',
  '#E4572E',
  '#F0A202',
  '#3D5A80',
  '#2A9D8F',
  '#E85D75',
  '#6C5CE7',
  '#E17055',
  '#0984E3',
  '#00B894',
  '#A35D6A',
];

function colorForKey(key) {
  let hash = 0;
  const value = String(key || '');
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return APP_COLORS[hash % APP_COLORS.length];
}

/**
 * Launcher / home page — shows every nav item the current user has access to
 * as a grid of app tiles, grouped by section. Single source of truth with the sidebar.
 */
const HomeGrid = ({ enabledModules, pwaInstallPrompt, onOpenSupport }) => {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { hospitalName } = useBranding();

  const roles = (() => {
    const r = user?.roles;
    if (Array.isArray(r) && r.length > 0) {
      return r.map((x) => (typeof x === 'string' ? x : x?.name)).filter(Boolean);
    }
    return user?.role ? [user.role] : [];
  })();
  const { sections } = useNavigationSections({ roles, enabledModules: enabledModules || {} });

  // Drop the duplicated "Dashboard" home tile — it appears in Tools instead.
  const visibleSections = sections
    .map(s => ({ ...s, items: s.items.filter(i => i.path !== '/dashboard') }))
    .filter(s => s.items.length > 0);

  const handleAddToDesktop = async () => {
    if (pwaInstallPrompt) {
      pwaInstallPrompt.prompt();
      await pwaInstallPrompt.userChoice;
    } else {
      const link = document.createElement('a');
      link.href = '/api/system/desktop-shortcut';
      link.download = 'KT HEALTH ERP.url';
      link.click();
    }
  };

  const toolsItems = [
    { text: 'Stats Dashboard', icon: <LayoutDashboard className="h-4 w-4" />, onClick: () => navigate('/dashboard') },
    { text: 'Help & Docs', icon: <BookOpen className="h-4 w-4" />, onClick: () => navigate('/help/docs') },
    { text: 'Add to Desktop', icon: <Monitor className="h-4 w-4" />, onClick: handleAddToDesktop },
    { text: 'Support', icon: <Headphones className="h-4 w-4" />, onClick: () => onOpenSupport && onOpenSupport() },
    { text: 'Log out', icon: <LogOut className="h-4 w-4" />, onClick: logout, danger: true },
  ];

  const Card = ({ icon, label, onClick, danger, colorKey }) => {
    const color = danger ? '#E4572E' : colorForKey(colorKey || label);
    return (
      <button
        type="button"
        onClick={onClick}
        title={label}
        className="group flex flex-col items-center justify-start gap-1 rounded-lg px-0.5 py-1.5 transition-colors duration-150 hover:bg-white hover:shadow-sm"
      >
        <span
          className="flex items-center justify-center h-9 w-9 rounded-lg text-white shadow-sm transition-transform duration-150 group-hover:scale-105"
          style={{ background: color }}
        >
          {icon}
        </span>
        <span className="text-[11px] font-medium text-center leading-tight text-gray-700 line-clamp-2 w-full">
          {label}
        </span>
      </button>
    );
  };

  const renderIcon = (item) => {
    if (!item?.icon) return null;
    return React.cloneElement(item.icon, { className: 'h-4 w-4' });
  };

  const firstName = user?.full_name ? user.full_name.split(' ')[0] : '';

  const tileGridClass = 'grid grid-cols-4 sm:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10 gap-x-1 gap-y-0.5';

  return (
    <div className="w-full px-2 py-2 sm:px-3">
      <div className="flex items-baseline justify-between gap-3 px-1 pb-2 mb-2 border-b border-gray-200/80">
        <h1 className="text-base font-semibold tracking-tight text-gray-900 truncate">
          {firstName ? `Welcome, ${firstName}` : 'Welcome'}
        </h1>
        <p className="text-xs font-medium text-primary truncate shrink-0">
          {hospitalName || 'KT HEALTH ERP'}
        </p>
      </div>

      <div className="space-y-2.5">
        {visibleSections.map((section, idx) => (
          <section key={section.label || `s-${idx}`}>
            {section.label && (
              <h2 className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-0.5 px-1">
                {section.label}
              </h2>
            )}
            <div className={tileGridClass}>
              {section.items.map(item => (
                <Card
                  key={item.path}
                  icon={renderIcon(item)}
                  label={item.text}
                  colorKey={item.path}
                  onClick={() => navigate(item.path)}
                />
              ))}
            </div>
          </section>
        ))}

        <section>
          <h2 className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-0.5 px-1">Tools</h2>
          <div className={tileGridClass}>
            {toolsItems.map(item => (
              <Card
                key={item.text}
                icon={item.icon}
                label={item.text}
                colorKey={item.text}
                onClick={item.onClick}
                danger={item.danger}
              />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
};

export default HomeGrid;
