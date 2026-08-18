import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, LogOut, Menu } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu';
import hospitalLogo from '../../assets/Final Logo KT (1).jpg';
import UniversalSearch from './UniversalSearch';

const idleLinkClass =
  'header-nav-link px-2.5 py-1.5 rounded-md text-sm font-medium whitespace-nowrap transition-colors flex-shrink-0';

/**
 * Top navigation bar for header layout mode — uses the same dark chrome as the sidebar.
 * Every module section is a first-class item on the bar (no More/Others overflow).
 */
export default function AppHeader({
  navigationSections,
  isActive,
  onOpenMobileMenu,
  logout,
  user,
  userInitials,
  roleLabel,
}) {
  const labeledSections = useMemo(
    () => (navigationSections || []).filter((section) => section.label),
    [navigationSections],
  );

  const sectionHasActive = (section) =>
    (section.items || []).some((item) => isActive(item.path));

  const idleStyle = { color: 'hsl(var(--sidebar-fg))' };
  const onIdleEnter = (e) => {
    e.currentTarget.style.background = 'hsl(var(--sidebar-hover))';
    e.currentTarget.style.color = '#fff';
  };
  const onIdleLeave = (e, active) => {
    if (active) return;
    e.currentTarget.style.background = 'transparent';
    e.currentTarget.style.color = 'hsl(var(--sidebar-fg))';
  };

  return (
    <header
      className="flex-shrink-0 z-40 border-b"
      style={{
        background: 'hsl(var(--sidebar-bg))',
        borderColor: 'hsl(var(--sidebar-border))',
      }}
    >
      <div className="flex items-center gap-2 h-14 px-3 lg:px-4">
        <button
          type="button"
          className="lg:hidden p-2 -ml-1 rounded-lg transition-colors"
          style={{ color: 'hsl(var(--sidebar-fg))' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'hsl(var(--sidebar-hover))';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
          }}
          onClick={onOpenMobileMenu}
          aria-label="Open menu"
        >
          <Menu className="h-5 w-5" />
        </button>

        <Link
          to="/dashboard"
          className="flex items-center flex-shrink-0 rounded"
          title="Dashboard"
          aria-label="Dashboard"
        >
          <img
            src={hospitalLogo}
            alt="KT Health Soft"
            className="h-8 w-auto max-w-[140px] rounded"
            style={{ filter: 'brightness(1.1) contrast(1.05)' }}
          />
        </Link>

        <nav className="header-nav hidden lg:flex items-center gap-0.5 flex-1 min-w-0 ml-2 overflow-x-auto">
          {labeledSections.map((section) => {
            const active = sectionHasActive(section);
            return (
              <DropdownMenu key={section.label}>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className={`${idleLinkClass} inline-flex items-center gap-1 ${
                      active ? 'header-nav-link-active' : ''
                    }`}
                    style={
                      active
                        ? { color: '#fff', background: 'hsl(var(--sidebar-active))' }
                        : idleStyle
                    }
                    onMouseEnter={(e) => {
                      if (!active) onIdleEnter(e);
                    }}
                    onMouseLeave={(e) => onIdleLeave(e, active)}
                  >
                    {section.label}
                    <ChevronDown className="h-3.5 w-3.5 opacity-60" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="min-w-[200px]">
                  {section.items.map((item) => (
                    <DropdownMenuItem key={item.text} asChild>
                      <Link
                        to={item.path}
                        className={`cursor-pointer ${isActive(item.path) ? 'font-semibold' : ''}`}
                      >
                        <span className="mr-2 opacity-70">{item.icon}</span>
                        {item.text}
                      </Link>
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            );
          })}
        </nav>

        <div className="flex items-center gap-2 ml-auto flex-shrink-0">
          <div className="hidden sm:block">
            <UniversalSearch
              navigationSections={navigationSections}
              triggerVariant="header"
            />
          </div>
          <div className="sm:hidden">
            <UniversalSearch
              navigationSections={navigationSections}
              triggerVariant="header-compact"
            />
          </div>

          <div
            className="hidden md:flex items-center gap-2 pl-2"
            style={{ borderLeft: '1px solid hsl(var(--sidebar-border))' }}
          >
            <div
              className="h-8 w-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 text-white"
              style={{ background: 'hsl(var(--sidebar-active))' }}
              title={roleLabel}
            >
              {userInitials}
            </div>
            <div className="hidden xl:block min-w-0 max-w-[120px]">
              <p className="text-sm font-medium truncate" style={{ color: '#fff' }}>
                {user?.full_name}
              </p>
              <p className="text-[11px] truncate" style={{ color: 'hsl(var(--sidebar-muted))' }}>
                {roleLabel}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={logout}
            className="p-2 rounded-lg transition-colors"
            style={{ color: 'hsl(var(--sidebar-fg))' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'hsla(0, 70%, 50%, 0.25)';
              e.currentTarget.style.color = '#fca5a5';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = 'hsl(var(--sidebar-fg))';
            }}
            title="Log out"
            aria-label="Log out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
