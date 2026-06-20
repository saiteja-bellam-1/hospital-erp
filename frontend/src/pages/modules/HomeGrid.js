import React from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, Monitor, Headphones, LogOut, LayoutDashboard } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { useNavigationSections } from '../../hooks/useNavigationSections';

/**
 * Launcher / home page — shows every nav item the current user has access to
 * as a grid of compact cards, grouped into per-section containers so partial
 * rows don't leave page-wide gaps. Single source of truth with the sidebar.
 */
const HomeGrid = ({ enabledModules, pwaInstallPrompt, onOpenSupport }) => {
  const navigate = useNavigate();
  const { user, logout, licenseStatus } = useAuth();

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
    { text: 'Stats Dashboard', icon: <LayoutDashboard className="h-5 w-5" />, onClick: () => navigate('/dashboard') },
    { text: 'Help & Docs', icon: <BookOpen className="h-5 w-5" />, onClick: () => navigate('/help/docs') },
    { text: 'Add to Desktop', icon: <Monitor className="h-5 w-5" />, onClick: handleAddToDesktop },
    ...(licenseStatus?.seller_info?.name
      ? [{ text: 'Support Contact', icon: <Headphones className="h-5 w-5" />, onClick: () => navigate('/dashboard/support-contact') }]
      : [{ text: 'Support', icon: <Headphones className="h-5 w-5" />, onClick: () => onOpenSupport && onOpenSupport() }]),
    { text: 'Log out', icon: <LogOut className="h-5 w-5" />, onClick: logout, danger: true },
  ];

  const Card = ({ icon, label, onClick, danger }) => (
    <button
      type="button"
      onClick={onClick}
      className={`
        group flex flex-col items-center justify-center gap-2
        rounded-xl border bg-white px-2 py-3 min-h-[88px]
        transition-all duration-150
        hover:-translate-y-0.5 hover:shadow-sm
        ${danger
          ? 'border-red-100 hover:border-red-300 hover:bg-red-50'
          : 'border-gray-200 hover:border-blue-300 hover:bg-blue-50/40'}
      `}
    >
      <span className={`
        flex items-center justify-center h-9 w-9 rounded-lg
        ${danger ? 'bg-red-50 text-red-600 group-hover:bg-red-100' : 'bg-blue-50 text-blue-600 group-hover:bg-blue-100'}
        transition-colors
      `}>
        {icon}
      </span>
      <span className={`text-[12px] font-medium text-center leading-tight ${danger ? 'text-red-700' : 'text-gray-800'}`}>
        {label}
      </span>
    </button>
  );

  const renderIcon = (item) => React.cloneElement(item.icon, { className: 'h-5 w-5' });

  const SectionHeader = ({ label }) => (
    <h2 className="col-span-full text-[11px] font-semibold tracking-wider uppercase text-gray-500 px-1 pt-2 first:pt-0">
      {label}
    </h2>
  );

  return (
    <div>
      {/* Header */}
      <div className="px-5 pt-5 pb-3">
        <h1 className="text-xl lg:text-2xl font-semibold text-gray-900">
          Welcome{user?.full_name ? `, ${user.full_name.split(' ')[0]}` : ''}
        </h1>
        <p className="text-xs text-gray-500 mt-0.5">
          Pick a module to get started — everything you have access to is shown below.
        </p>
      </div>

      {/* Single bordered container — all items in a unified 6-column grid, flush to page edges */}
      <div className="border-y border-blue-200 bg-white/70 backdrop-blur-sm p-5 shadow-sm">
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3">
          {visibleSections.map((section, idx) => (
            <React.Fragment key={section.label || `s-${idx}`}>
              {section.label && <SectionHeader label={section.label} />}
              {section.items.map(item => (
                <Card
                  key={item.path}
                  icon={renderIcon(item)}
                  label={item.text}
                  onClick={() => navigate(item.path)}
                />
              ))}
            </React.Fragment>
          ))}

          <SectionHeader label="Tools" />
          {toolsItems.map(item => (
            <Card key={item.text} icon={item.icon} label={item.text} onClick={item.onClick} danger={item.danger} />
          ))}
        </div>
      </div>
    </div>
  );
};

export default HomeGrid;
