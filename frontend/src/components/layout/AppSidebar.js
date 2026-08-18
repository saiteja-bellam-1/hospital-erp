import React from 'react';
import { Link } from 'react-router-dom';
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  LogOut,
  Monitor,
  X,
} from 'lucide-react';
import hospitalLogo from '../../assets/Final Logo KT (1).jpg';
import UniversalSearch from './UniversalSearch';

/**
 * Left sidebar / mobile drawer navigation chrome.
 */
export default function AppSidebar({
  sidebarOpen,
  onClose,
  navigationSections,
  collapsedSections,
  onToggleSection,
  isActive,
  hideOnDesktop = false,
  showSearch = true,
  pwaInstallPrompt,
  setPwaInstallPrompt,
  logout,
  user,
  userInitials,
  roleLabel,
}) {
  return (
    <aside
      className={`
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        fixed inset-y-0 left-0 z-50 w-[260px] flex flex-col
        transform transition-transform duration-300 ease-in-out
        ${hideOnDesktop ? 'lg:hidden' : 'lg:translate-x-0 lg:static lg:inset-0'}
      `}
      style={{
        background: 'hsl(var(--sidebar-bg))',
        borderRight: '1px solid hsl(var(--sidebar-border))',
      }}
    >
      <div
        className="flex items-center justify-between h-16 px-5 flex-shrink-0"
        style={{ borderBottom: '1px solid hsl(var(--sidebar-border))' }}
      >
        <Link to="/dashboard" className="flex items-center gap-2" title="Dashboard" aria-label="Dashboard">
          <img
            src={hospitalLogo}
            alt="KT Health Soft"
            className="h-9 w-auto max-w-[180px] rounded"
            style={{ filter: 'brightness(1.1) contrast(1.05)' }}
          />
        </Link>
        <button
          className={`${hideOnDesktop ? '' : 'lg:hidden '}p-1 rounded-md hover:bg-white/10 transition-colors`}
          style={{ color: 'hsl(var(--sidebar-fg))' }}
          onClick={onClose}
          type="button"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {showSearch && (
        <div className="px-3 pt-3">
          <UniversalSearch
            navigationSections={navigationSections}
            triggerVariant="sidebar"
          />
        </div>
      )}

      <nav className="sidebar-nav flex-1 overflow-y-auto py-4 px-3">
        {navigationSections.filter((section) => section.label).map((section, sIdx) => {
          const isCollapsible = !!section.label;
          const isCollapsed = isCollapsible && collapsedSections[section.label] !== false;
          return (
            <div key={section.label || `section-${sIdx}`} className={sIdx > 0 ? 'mt-3' : ''}>
              {isCollapsible && (
                <button
                  type="button"
                  onClick={() => onToggleSection(section.label)}
                  className="w-full flex items-center justify-between px-3 mb-1 py-1.5 rounded-md text-[11px] font-semibold tracking-wider uppercase transition-colors"
                  style={{ color: 'hsl(var(--sidebar-muted))' }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'hsl(var(--sidebar-hover))';
                    e.currentTarget.style.color = '#fff';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'transparent';
                    e.currentTarget.style.color = 'hsl(var(--sidebar-muted))';
                  }}
                >
                  <span>{section.label}</span>
                  {isCollapsed ? (
                    <ChevronRight className="h-3.5 w-3.5 opacity-70" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5 opacity-70" />
                  )}
                </button>
              )}
              {!isCollapsed && (
                <div className="space-y-0.5">
                  {section.items.map((item) => {
                    const active = isActive(item.path);
                    return (
                      <Link
                        key={item.text}
                        to={item.path}
                        className={`
                          group flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13.5px] font-medium
                          transition-all duration-150 relative
                          ${active ? 'nav-item-active' : ''}
                        `}
                        style={{
                          color: active ? '#fff' : 'hsl(var(--sidebar-fg))',
                          background: active ? 'hsl(var(--sidebar-active))' : 'transparent',
                        }}
                        onMouseEnter={(e) => {
                          if (!active) {
                            e.currentTarget.style.background = 'hsl(var(--sidebar-hover))';
                            e.currentTarget.style.color = '#fff';
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!active) {
                            e.currentTarget.style.background = 'transparent';
                            e.currentTarget.style.color = 'hsl(var(--sidebar-fg))';
                          }
                        }}
                      >
                        <span
                          className="flex-shrink-0 opacity-80 group-hover:opacity-100"
                          style={active ? { opacity: 1 } : {}}
                        >
                          {item.icon}
                        </span>
                        <span className="truncate">{item.text}</span>
                        {active && <ChevronRight className="h-3.5 w-3.5 ml-auto opacity-60" />}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      <div className="mx-3 my-1" style={{ borderTop: '1px solid hsl(var(--sidebar-border))' }} />

      <div className="px-3 pb-1">
        <Link
          to="/help/docs"
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-all duration-150"
          style={{ color: 'hsl(var(--sidebar-fg))' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'hsl(var(--sidebar-hover))';
            e.currentTarget.style.color = '#fff';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
            e.currentTarget.style.color = 'hsl(var(--sidebar-fg))';
          }}
        >
          <BookOpen className="h-[18px] w-[18px] opacity-80" />
          <span>Help & Docs</span>
        </Link>
      </div>

      <div className="px-3 pb-1">
        <button
          type="button"
          onClick={async () => {
            if (pwaInstallPrompt) {
              pwaInstallPrompt.prompt();
              const result = await pwaInstallPrompt.userChoice;
              if (result.outcome === 'accepted') setPwaInstallPrompt(null);
            } else {
              const link = document.createElement('a');
              link.href = '/api/system/desktop-shortcut';
              link.download = 'KT HEALTH ERP.url';
              link.click();
            }
          }}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-all duration-150 w-full"
          style={{ color: 'hsl(var(--sidebar-fg))' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'hsl(var(--sidebar-hover))';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
          }}
        >
          <Monitor className="h-[18px] w-[18px] opacity-80" />
          <span>Add to Desktop</span>
        </button>
      </div>

      <div className="px-3 pb-1">
        <button
          type="button"
          onClick={logout}
          className="flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-all duration-150 w-full"
          style={{ color: 'hsl(var(--sidebar-fg))' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'hsla(0, 70%, 50%, 0.25)';
            e.currentTarget.style.color = '#fca5a5';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
            e.currentTarget.style.color = 'hsl(var(--sidebar-fg))';
          }}
        >
          <LogOut className="h-[18px] w-[18px] opacity-80" />
          <span>Log out</span>
        </button>
      </div>

      <div className="flex-shrink-0 p-3" style={{ borderTop: '1px solid hsl(var(--sidebar-border))' }}>
        <div
          className="flex items-center gap-3 px-2 py-2 rounded-lg"
          style={{ background: 'hsl(var(--sidebar-hover))' }}
        >
          <div
            className="h-8 w-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
            style={{
              background: 'hsl(var(--sidebar-active))',
              color: '#fff',
            }}
          >
            {userInitials}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate" style={{ color: '#fff' }}>
              {user?.full_name}
            </p>
            <p className="text-[11px] truncate" style={{ color: 'hsl(var(--sidebar-muted))' }}>
              {roleLabel}
            </p>
          </div>
        </div>
      </div>
    </aside>
  );
}
