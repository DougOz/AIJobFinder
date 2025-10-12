import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { FileText, CheckCircle, ChevronLeft, ChevronRight, Briefcase, MapPin, DollarSign, Calendar, ThumbsUp, ThumbsDown, X } from 'lucide-react';

// --- Configuration & Types ---
const API_BASE_URL = 'http://localhost:5000/api';
const DEFAULT_PROFILE_NAME = 'JobRaterUser';

// CRITICAL: Define skill levels with specific hex codes for INLINE styling
const SKILL_LEVELS = {
    0: { label: 'Not Rated (0)', bgColor: '#e5e7eb', textColor: '#374151', hoverBgColor: '#f3f4f6' },
    1: { label: 'Novice (1)', bgColor: '#fee2e2', textColor: '#b91c1c', hoverBgColor: '#fecaca' },
    2: { label: 'Proficient (2)', bgColor: '#fef3c7', textColor: '#b45309', hoverBgColor: '#fde68a' },
    3: { label: 'Expert (3)', bgColor: '#d1fae5', textColor: '#047857', hoverBgColor: '#a7f3d0' },
};

// Define commonly used hex codes as JS constants for use in React's inline styles
const COLORS = {
    indigo600: '#4f46e5',
    indigo700: '#4338ca',
    indigo500: '#6366f1',
    gray900: '#111827',
    gray800: '#1f2937',
    gray600: '#4b5563',
    gray500: '#6b7280',
    green600: '#10b981',
    green700: '#047857',
    red600: '#dc2626',
    red700: '#b91c1c',
    yellow500: '#f59e0b',
};

interface Highlight {
    text: string;
    type: 'like' | 'dislike';
}

interface JobDetails {
    job_id: string;
    url: string;
    title: string;
    company: string;
    location: string;
    posted_date: string;
    job_types: string[];
    salary: string;
    skills: string[];
    description: string;
    resume_score: number;
    semantic_score_v2: number;
}

interface SkillProficiency {
    skill_name: string;
    user_rating: number;
}

// Interface expects the backend to return user's saved data
interface FetchedData {
    job_details: JobDetails;
    skill_proficiencies: SkillProficiency[];
    existing_highlights: Highlight[];
    user_overall_score: number | null;
    user_notes: string | null;
    source: string;
    error?: string;
}

// --- Floating Highlight Menu Component ---
interface FloatingMenuProps {
    x: number;
    y: number;
    onSelect: (type: 'like' | 'dislike') => void;
    menuRef: React.RefObject<HTMLDivElement>;
}

const FloatingMenu: React.FC<FloatingMenuProps> = ({ x, y, onSelect, menuRef }) => {
    const style = {
        left: `${x}px`,
        top: `${y}px`,
        transform: 'translateX(-50%) translateY(calc(-100% - 10px))',
    };

    return (
        <div
            ref={menuRef}
            style={style}
            className="floating-menu"
            onMouseDown={(e) => e.stopPropagation()}
        >
            <button
                onClick={(e) => { e.stopPropagation(); onSelect('like'); }}
                className="menu-button-like"
                title="Mark as LIKED"
            >
                <ThumbsUp size={16} />
            </button>
            <button
                onClick={(e) => { e.stopPropagation(); onSelect('dislike'); }}
                className="menu-button-dislike"
                title="Mark as DISLIKED"
            >
                <ThumbsDown size={16} />
            </button>
        </div>
    );
};


// --- Main App Component ---
export default function App() {
    // Default score to 0 to represent "Not Rated"
    const [overallScore, setOverallScore] = useState(0);
    const [notes, setNotes] = useState('');

    const [job, setJob] = useState<JobDetails | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [jobIds, setJobIds] = useState<string[]>([]);
    const [currentJobIndex, setCurrentJobIndex] = useState<number>(0);
    const currentJobId = useMemo(() => jobIds[currentJobIndex], [jobIds, currentJobIndex]);

    const [submissionStatus, setSubmissionStatus] = useState<string | null>(null);
    const [skillProficiencies, setSkillProficiencies] = useState<Record<string, number>>({});
    const [highlights, setHighlights] = useState<Highlight[]>([]);

    // Menu state updated to store the text 
    const [floatingMenu, setFloatingMenu] = useState<{ x: number, y: number, text: string } | null>(null);

    const descriptionRef = useRef<HTMLDivElement>(null);
    const menuRef = useRef<HTMLDivElement>(null);


    // --- Data Fetching Hooks (Job List and Job Data) ---
    useEffect(() => {
        const fetchJobList = async () => {
            setLoading(true);
            try {
                const response = await fetch(`${API_BASE_URL}/jobs/list`);
                if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
                const data = await response.json();
                const ids: string[] = data.job_ids;
                setJobIds(ids);
                if (ids.length > 0) {
                    setCurrentJobIndex(0);
                } else {
                    setError("The server returned an empty list of job IDs. Please ensure your MongoDB 'jobs' collection is populated.");
                }
            } catch (err) {
                setError(`Failed to fetch job list. Check server and MongoDB connection. Error: ${(err as Error).message}`);
            }
        };
        fetchJobList();
    }, []);

    const fetchJobData = async (jobId: string) => {
        if (!jobId) return;

        setLoading(true);
        setJob(null);

        // Reset state before fetching new job data to prevent carry-over
        setOverallScore(0);
        setNotes('');
        setHighlights([]);
        setFloatingMenu(null);

        try {
            const response = await fetch(`${API_BASE_URL}/job/${jobId}`);
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);

            const data: FetchedData = await response.json();

            if (data.error) throw new Error(data.error);

            setJob(data.job_details);

            // CRITICAL PERSISTENCE FIX: Ensure score is treated as a number or defaults to 0
            // This will load the value saved in MongoDB.
            const savedScore = Number(data.user_overall_score) || 0;
            setOverallScore(savedScore);
            setNotes(data.user_notes ?? '');

            const profMap = data.skill_proficiencies.reduce((acc: Record<string, number>, curr) => {
                acc[curr.skill_name] = Math.min(3, Math.max(0, curr.user_rating));
                return acc;
            }, {});
            setSkillProficiencies(profMap);

            setHighlights(data.existing_highlights || []);

        } catch (err) {
            console.error("Fetch error:", err);
            setError(`Failed to load job ${jobId}. Error: ${(err as Error).message}`);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (currentJobId) {
            fetchJobData(currentJobId);
        }
    }, [currentJobId]);


    // --- Navigation & Skill Logic ---
    const navigateJob = (direction: 'prev' | 'next') => {
        const newIndex = direction === 'next' ? currentJobIndex + 1 : currentJobIndex - 1;
        if (newIndex >= 0 && newIndex < jobIds.length) {
            setCurrentJobIndex(newIndex);
            setSubmissionStatus(null);
            window.scrollTo(0, 0);
        }
    };

    const isPrevDisabled = currentJobIndex === 0;
    const isNextDisabled = jobIds.length > 0 && currentJobIndex === jobIds.length - 1;

    const relevantSkills = useMemo(() => {
        if (!job) return [];

        return job.skills.map(skillName => ({
            name: skillName,
        })).sort((a, b) => {
            const ratingA = skillProficiencies[a.name] || 0;
            const ratingB = skillProficiencies[b.name] || 0;
            return ratingB - ratingA;
        });
    }, [job, skillProficiencies]);

    const handleSkillUpdate = (skillName: string, newRating: number) => {
        const cappedRating = Math.min(3, Math.max(0, newRating));
        setSkillProficiencies(prev => ({
            ...prev,
            [skillName]: cappedRating,
        }));
    };

    // --- Highlighting Logic ---

    const handleMouseUp = useCallback(() => {
        const selection = window.getSelection();
        const selectedText = selection?.toString().trim();

        // Check if the selection is valid and is inside the description area
        if (selectedText && selectedText.length > 3 && descriptionRef.current?.contains(selection!.anchorNode!)) {
            try {
                const range = selection!.getRangeAt(0);
                const rect = range.getBoundingClientRect();

                // Calculate menu position
                const x = rect.left + window.scrollX + rect.width / 2;
                const y = rect.top + window.scrollY;

                // Store the selected text and position, DO NOT clear the selection yet
                setFloatingMenu({ x, y, text: selectedText });
            } catch (e) {
                console.error("Error getting selection bounding box:", e);
                setFloatingMenu(null);
            }
        } else {
            // Only clear if the menu is not active, or if selection is collapsed
            if (selection?.isCollapsed) {
                setFloatingMenu(null);
            }
        }
    }, []);

    // Refined function to handle mouse clicks outside the menu
    const handleMouseDownOutside = useCallback((e: MouseEvent) => {
        // If a click happens and the target is NOT the floating menu, hide it.
        if (floatingMenu && menuRef.current && !menuRef.current.contains(e.target as Node)) {
            setFloatingMenu(null);
        }
    }, [floatingMenu]);

    useEffect(() => {
        document.addEventListener('mouseup', handleMouseUp);
        document.addEventListener('mousedown', handleMouseDownOutside);

        return () => {
            document.removeEventListener('mouseup', handleMouseUp);
            document.removeEventListener('mousedown', handleMouseDownOutside);
        };
    }, [handleMouseUp, handleMouseDownOutside]);

    // Handle menu selection (Like/Dislike)
    const handleHighlightSelection = (type: 'like' | 'dislike') => {
        if (!floatingMenu) return;

        const newHighlight: Highlight = { text: floatingMenu.text, type };

        // Check for duplicates before adding
        const exists = highlights.some(h => h.text === newHighlight.text);

        if (!exists) {
            setHighlights(prev => [...prev, newHighlight]);
        }

        // Clear the selection and hide the menu only after successful action
        window.getSelection()?.removeAllRanges();
        setFloatingMenu(null);
    };

    // Render the description with highlights applied using robust inline styles
    const renderDescription = useMemo(() => (description: string) => {
        let content = description;

        highlights.forEach(h => {
            // Guaranteed inline styles for highlight colors
            const style = h.type === 'like'
                ? "background-color: #d1fae5; color: #065f46; border-radius: 4px; padding: 1px 4px; font-weight: 600;"
                : "background-color: #fee2e2; color: #991b1b; border-radius: 4px; padding: 1px 4px; font-weight: 600;";

            // Escape special regex characters
            const safeText = h.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            // Find the whole word/phrase match
            const regex = new RegExp(`(${safeText})`, 'gi');

            // Use a function in replace to avoid re-matching inside already highlighted spans
            content = content.replace(regex, (match, p1, offset, string) => {
                // Simple check to prevent highlighting within an existing span (not perfect but helps)
                const precedingHtml = string.substring(0, offset);
                if (precedingHtml.endsWith('</span>')) return match;
                return `<span style="${style}">${p1}</span>`;
            });
        });

        return <div dangerouslySetInnerHTML={{ __html: content.replace(/\n/g, '<br/>') }} />;
    }, [highlights]);

    // Remove a highlight
    const removeHighlight = (indexToRemove: number) => {
        setHighlights(prev => prev.filter((_, index) => index !== indexToRemove));
    };


    // --- Submission Logic (Verified to include overallScore and notes) ---
    const handleSubmit = async () => {
        if (!job) return;

        setSubmissionStatus("Submitting...");

        // Ensure the user has rated before submitting a score > 0
        if (overallScore === 0) {
            setSubmissionStatus("Please rate the job before submitting (1-10).");
            setTimeout(() => setSubmissionStatus(null), 3000);
            return;
        }

        const ratedSkills = relevantSkills.map(s => ({
            skill_name: s.name,
            user_rating: skillProficiencies[s.name] || 0
        }));

        // These values are correctly pulled from state (which loaded them from Mongo)
        const submissionData = {
            job_id: job.job_id,
            profile_id: DEFAULT_PROFILE_NAME,
            overall_score: overallScore,
            notes: notes,
            highlights: highlights,
            rated_skills: ratedSkills,
            timestamp: new Date().toISOString(),
            source: "Manual Rater V10 (MongoDB)"
        };

        try {
            const response = await fetch(`${API_BASE_URL}/rate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(submissionData),
            });

            if (!response.ok) throw new Error(`Submission failed with status: ${response.status}`);

            setSubmissionStatus("Rating saved successfully!");
            // Navigate immediately after successful save
            setTimeout(() => navigateJob('next'), 500);

        } catch (err) {
            console.error("Submission error:", err);
            setSubmissionStatus(`Error saving rating: ${(err as Error).message}`);
        }
    };


    // --- Render Logic ---
    const displayScore = overallScore === 0 ? 'Not Rated' : overallScore;
    const scoreColor = overallScore === 0 ? COLORS.gray600 : COLORS.indigo600;

    if (error) {
        return (
            <div className="error-card">
                <h2 className="text-xl font-bold mb-2">Application Error</h2>
                <p>{error}</p>
                <p className="mt-4 text-sm">Action required: Ensure your Flask server is running and connected to MongoDB.</p>
            </div>
        );
    }

    return (
        <div className="app-container">
            {/* FULLY COMPILED CSS TO REPLACE TAILWIND JIT - ALL CSS VARIABLES MOVED TO THIS BLOCK */}
            <style>{`
        /* --- GLOBAL STYLES & LAYOUT --- */
        /* CSS Variables are only used within this style block */
        :root {
            --indigo-600: #4f46e5;
            --indigo-700: #4338ca;
            --indigo-500: #6366f1;
            --indigo-50: #eef2ff;
            --gray-900: #111827;
            --gray-800: #1f2937;
            --gray-700: #374151;
            --gray-600: #4b5563;
            --gray-500: #6b7280;
            --gray-200: #e5e7eb;
            --gray-100: #f3f4f6;
            --gray-50: #f9fafb;
            --green-600: #10b981;
            --green-700: #047857;
            --red-500: #ef4444;
            --red-600: #dc2626;
            --yellow-500: #f59e0b;
        }

        .app-container {
            min-height: 100vh;
            background: linear-gradient(to bottom right, var(--gray-50), var(--indigo-50));
            padding: 1rem;
            font-family: 'Inter', sans-serif;
        }
        @media (min-width: 640px) {
            .app-container { padding: 2rem; }
        }
        
        .main-container {
            max-width: 1280px;
            margin: 0 auto;
            background-color: #fff;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
            border-radius: 1rem;
            padding: 1.5rem;
            border-top: 8px solid var(--indigo-600);
        }
        @media (min-width: 640px) {
            .main-container { padding: 2.5rem; }
        }

        /* --- NAVIGATION HEADER --- */
        .nav-header {
            max-width: 1280px;
            margin: 0 auto 1.5rem auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 40;
            padding: 0.75rem;
            background-color: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(4px);
            border-bottom-left-radius: 0.75rem;
            border-bottom-right-radius: 0.75rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
        }

        .nav-controls {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            background-color: #fff;
            padding: 0.25rem;
            border-radius: 9999px;
            box-shadow: inset 0 2px 4px 0 rgba(0, 0, 0, 0.06);
            border: 1px solid var(--gray-200);
        }

        .nav-button {
            display: flex;
            align-items: center;
            padding: 0.5rem 1rem;
            border-radius: 9999px;
            font-weight: 600;
            transition: all 150ms ease-in-out;
        }

        .nav-button-prev {
            background-color: var(--indigo-50);
            color: var(--indigo-700);
        }
        .nav-button-prev:hover:not(:disabled) { background-color: var(--gray-100); }
        .nav-button-next {
            background-color: var(--indigo-600);
            color: #fff;
            box-shadow: 0 10px 15px -3px rgba(79, 70, 229, 0.3), 0 4px 6px -4px rgba(79, 70, 229, 0.1);
        }
        .nav-button-next:hover:not(:disabled) { background-color: var(--indigo-700); }
        .nav-button:disabled { opacity: 0.5; cursor: not-allowed; }
        .nav-button-next:disabled { background-color: #a5b4fc; }

        /* --- LOADING STATE --- */
        .animate-spin { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

        /* --- MAIN GRID LAYOUT --- */
        .main-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 2.5rem;
        }
        @media (min-width: 1024px) {
            .main-grid { grid-template-columns: 1fr 2fr; }
        }

        /* --- CARDS & PANELS --- */
        .card-base {
            padding: 1.5rem;
            border-radius: 0.75rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
        }
        .card-metrics {
            background-color: var(--indigo-50);
            border: 2px solid #c7d2fe;
            box-shadow: inset 0 2px 4px 0 rgba(0, 0, 0, 0.05);
        }
        .card-score {
            background-color: #fff;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.1);
            border: 1px solid var(--gray-200);
        }
        .card-skills, .card-notes {
            background-color: var(--gray-50);
            border: 1px solid var(--gray-200);
        }
        .skill-item {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            align-items: flex-start;
            padding: 0.75rem;
            border-radius: 0.75rem;
            background-color: #fff;
            box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            border: 1px solid var(--gray-100);
        }
        @media (min-width: 640px) {
            .skill-item { flex-direction: row; align-items: center; }
        }

        /* --- SKILL SELECT DROPDOWN (Custom Styling) --- */
        .skill-select {
            padding: 0.25rem 0.75rem;
            font-size: 0.875rem; 
            font-weight: 600;
            border-radius: 0.5rem;
            border: 2px solid #a5b4fc; 
            box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            appearance: none; 
            width: 10rem;
            text-align: center;
            background-repeat: no-repeat;
            background-position: right 0.5rem center;
            background-size: 1.5em 1.5em;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='%234F46E5'%3E%3Cpath fill-rule='evenodd' d='M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.25 4.25a.75.75 0 01-1.06 0L5.21 8.27a.75.75 0 01.02-1.06z' clip-rule='evenodd' /%3E%3C/svg%3E");
        }

        /* --- HIGHLIGHT MENU --- */
        .floating-menu {
            position: absolute; 
            z-index: 50;
            display: flex;
            gap: 0.5rem;
            padding: 0.375rem;
            background-color: var(--gray-700);
            border-radius: 9999px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
            transition: all 100ms ease-out;
            border: 2px solid #818cf8; /* indigo-400 */
        }
        .menu-button-like, .menu-button-dislike {
            padding: 0.375rem;
            color: #fff;
            border-radius: 9999px;
            transition: background-color 150ms ease-in-out;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .menu-button-like { background-color: #10b981; } /* green-500 */
        .menu-button-like:hover { background-color: #059669; } /* green-600 */
        .menu-button-dislike { background-color: var(--red-500); }
        .menu-button-dislike:hover { background-color: var(--red-600); }

        /* --- SUBMISSION BUTTON --- */
        .submit-button {
            width: 100%;
            background-color: var(--indigo-600);
            color: #fff;
            font-weight: 900;
            padding: 1rem 1.5rem;
            border-radius: 0.75rem;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
            transition: background-color 150ms ease-in-out;
            font-size: 1.125rem;
        }
        .submit-button:hover:not(:disabled) { background-color: var(--indigo-700); }
        .submit-button:disabled { background-color: #a5b4fc; cursor: not-allowed; }

        /* --- HIGHLIGHT LIST ITEMS --- */
        .highlight-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.5rem;
            border-radius: 0.5rem;
            font-size: 0.875rem;
            font-weight: 500;
            transition: background-color 150ms ease-in-out;
        }
        .highlight-like {
            background-color: #d1fae5;
            border-left: 4px solid #059669;
            color: #065f46;
        }
        .highlight-dislike {
            background-color: #fee2e2;
            border-left: 4px solid var(--red-600);
            color: var(--red-700);
        }
        .highlight-remove-btn {
            margin-left: 0.5rem;
            padding: 0 0.5rem;
            font-size: 0.75rem;
            color: var(--gray-500);
            background-color: #fff;
            border-radius: 9999px;
            transition: color 150ms ease-in-out;
            font-weight: 700;
        }
        .highlight-remove-btn:hover { color: var(--gray-800); }

        /* --- ERROR MESSAGE --- */
        .error-card {
            padding: 2rem;
            background-color: #fee2e2;
            border-left: 4px solid var(--red-500);
            color: var(--red-700);
            font-family: monospace;
            max-width: 90%;
            margin: 2rem auto;
            border-radius: 0.5rem;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        }
      `}</style>

            {/* Navigation Header */}
            <div className="nav-header">
                <h1 className="text-2xl sm:text-3xl font-black" style={{ color: COLORS.indigo700 }}>Job Rater Pro</h1>
                <div className="nav-controls">
                    <button
                        onClick={() => navigateJob('prev')}
                        disabled={isPrevDisabled || loading}
                        className="nav-button nav-button-prev flex items-center"
                    >
                        <ChevronLeft size={18} style={{ marginRight: '4px' }} /> Prev
                    </button>

                    <span className="text-sm font-semibold" style={{ color: COLORS.gray600 }}>
                        {currentJobIndex + 1} of {jobIds.length}
                    </span>

                    <button
                        onClick={() => navigateJob('next')}
                        disabled={isNextDisabled || loading}
                        className="nav-button nav-button-next flex items-center"
                    >
                        Next <ChevronRight size={18} style={{ marginLeft: '4px' }} />
                    </button>
                </div>
            </div>


            {/* Main Content Card */}
            <div className="main-container">

                {loading || !job ? (
                    <div className="flex flex-col items-center justify-center min-h-[400px]">
                        <div className="w-12 h-12 border-4 border-t-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
                        <div className="text-xl mt-4" style={{ color: COLORS.indigo600 }}>Loading Job {currentJobId || '...'}</div>
                    </div>
                ) : (
                    <>
                        {/* Job Header */}
                        <header style={{ marginBottom: '2rem', borderBottom: '1px solid #e5e7eb', paddingBottom: '1rem' }}>
                            <p style={{ fontSize: '0.875rem', color: COLORS.gray500, marginBottom: '0.25rem' }}>Job ID: {job.job_id} | <a href={job.url} target="_blank" style={{ color: COLORS.indigo500, textDecoration: 'underline' }}>View Source</a></p>
                            <h2 style={{ fontSize: '2.25rem', fontWeight: 800, color: COLORS.gray900, lineHeight: 1.25 }}>{job.title}</h2>
                            <p style={{ fontSize: '1.25rem', fontWeight: 500, color: COLORS.indigo600, marginTop: '0.5rem' }}>
                                {job.company} — <span style={{ color: COLORS.gray500, fontWeight: 400 }}>{job.location}</span>
                            </p>
                        </header>

                        {/* Main Content Grid */}
                        <div className="main-grid">

                            {/* LEFT COLUMN: Job Metrics & Metadata */}
                            <div className="lg-col-span-1" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

                                {/* Summary Metadata Section */}
                                <div className="card-base card-metrics">
                                    <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: COLORS.indigo700, marginBottom: '1rem', display: 'flex', alignItems: 'center' }}><Briefcase style={{ marginRight: '0.5rem' }} size={20} /> Job Metrics</h3>
                                    <dl style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '1rem', color: '#374151' }}>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>
                                            <MapPin size={18} style={{ color: COLORS.indigo500, marginRight: '0.75rem', flexShrink: 0 }} />
                                            <dt style={{ fontWeight: 500, color: COLORS.gray600, width: '33.33%' }}>Location:</dt>
                                            <dd style={{ fontWeight: 600 }}>{job.location || 'N/A'}</dd>
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>
                                            <DollarSign size={18} style={{ color: COLORS.indigo500, marginRight: '0.75rem', flexShrink: 0 }} />
                                            <dt style={{ fontWeight: 500, color: COLORS.gray600, width: '33.33%' }}>Salary:</dt>
                                            <dd style={{ fontWeight: 600, color: COLORS.green700 }}>{job.salary || 'N/A'}</dd>
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center' }}>
                                            <Calendar size={18} style={{ color: COLORS.indigo500, marginRight: '0.75rem', flexShrink: 0 }} />
                                            <dt style={{ fontWeight: 500, color: COLORS.gray600, width: '33.33%' }}>Posted:</dt>
                                            <dd>{job.posted_date}</dd>
                                        </div>
                                        <div style={{ paddingTop: '0.75rem', borderTop: '1px solid #e5e7eb', marginTop: '0.75rem' }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                <dt style={{ fontWeight: 700, color: COLORS.gray800 }}>Resume Match Score:</dt>
                                                <dd style={{ fontSize: '1.5rem', fontWeight: 900, color: COLORS.green600 }}>{(job.resume_score || 0).toFixed(1)}%</dd>
                                            </div>
                                        </div>
                                    </dl>
                                </div>

                                {/* Overall Match Score */}
                                <div className="card-base card-score">
                                    <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: COLORS.gray800, marginBottom: '1rem', display: 'flex', alignItems: 'center' }}><CheckCircle style={{ marginRight: '0.5rem', color: COLORS.indigo600 }} size={22} /> Overall Match Score</h3>
                                    <p style={{ fontSize: '0.875rem', color: COLORS.gray600, marginBottom: '1rem' }}>Rate the fit from 1 (Poor) to 10 (Perfect). **Currently {displayScore}**.</p>

                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                                        <span style={{ fontSize: '2.25rem', fontWeight: 800, color: scoreColor }}>
                                            {displayScore}
                                        </span>
                                        <span style={{ fontSize: '1.125rem', color: COLORS.gray500 }}>/ 10</span>
                                    </div>

                                    {/* Render the slider only if the score is > 0 or if the user is interacting */}
                                    {(overallScore > 0 || loading === false) && (
                                        <input
                                            type="range"
                                            min="1"
                                            max="10"
                                            step="1"
                                            // If score is 0, set slider to 5 as a neutral starting point for interaction
                                            value={overallScore || 5}
                                            onChange={(e) => setOverallScore(parseInt(e.target.value))}
                                            style={{ width: '100%', height: '0.75rem', backgroundColor: '#eef2ff', borderRadius: '0.5rem', appearance: 'none', cursor: 'pointer', accentColor: COLORS.indigo600 }}
                                        />
                                    )}
                                    {overallScore === 0 && (
                                        <button
                                            onClick={() => setOverallScore(5)}
                                            style={{ width: '100%', padding: '0.75rem', borderRadius: '0.5rem', backgroundColor: COLORS.indigo600, color: 'white', fontWeight: 600, transition: 'background-color 150ms' }}
                                        >
                                            Start Rating (Set to 5)
                                        </button>
                                    )}
                                </div>
                            </div>


                            {/* RIGHT COLUMN: Rating Controls, Skills, Description */}
                            <div className="lg-col-span-2" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>

                                {/* 1. Skills Proficiency Review */}
                                <div className="card-base card-skills" style={{ boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}>
                                    <h3 style={{ fontSize: '1.5rem', fontWeight: 600, color: COLORS.gray800, marginBottom: '1.5rem' }}>Skill Proficiency Update</h3>

                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                        {relevantSkills.map(skill => {
                                            const currentRating = Math.min(3, skillProficiencies[skill.name] || 0);
                                            const { bgColor, textColor } = SKILL_LEVELS[currentRating];

                                            return (
                                                <div key={skill.name} className="skill-item">
                                                    <span style={{ fontWeight: 700, color: COLORS.gray900, flexGrow: 1, marginRight: '1rem' }}>{skill.name}</span>

                                                    <select
                                                        value={currentRating}
                                                        onChange={(e) => handleSkillUpdate(skill.name, parseInt(e.target.value))}
                                                        className={`skill-select`}
                                                        style={{ backgroundColor: bgColor, color: textColor }}
                                                    >
                                                        {Object.entries(SKILL_LEVELS).map(([value, { label }]) => (
                                                            <option key={value} value={value} style={{ color: COLORS.gray900, backgroundColor: '#fff' }}>
                                                                {label}
                                                            </option>
                                                        ))}
                                                    </select>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>

                                {/* 2. Job Description Section */}
                                <div>
                                    <h3 style={{ fontSize: '1.5rem', fontWeight: 600, color: COLORS.gray800, marginBottom: '1rem', display: 'flex', alignItems: 'center' }}><FileText style={{ marginRight: '0.5rem' }} size={20} /> Job Description</h3>
                                    <div
                                        ref={descriptionRef}
                                        style={{
                                            color: COLORS.gray700,
                                            border: '1px solid #d1d5db',
                                            padding: '1.5rem',
                                            borderRadius: '0.75rem',
                                            backgroundColor: '#fff',
                                            boxShadow: 'inset 0 2px 4px 0 rgba(0, 0, 0, 0.05)',
                                            userSelect: 'text',
                                            whiteSpace: 'pre-wrap'
                                        }}
                                    >
                                        <p style={{ fontSize: '0.875rem', color: COLORS.indigo600, fontWeight: 700, marginBottom: '1rem', borderBottom: '1px solid #e5e7eb', paddingBottom: '0.5rem' }}>
                                            Action: **HIGHLIGHT TEXT** to make the floating Like/Dislike menu appear.
                                        </p>
                                        {renderDescription(job.description || "No description provided.")}
                                    </div>
                                </div>

                                {/* 3. Notes & Highlights Summary */}
                                <div className="card-base card-notes" style={{ backgroundColor: '#fff' }}>
                                    <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: COLORS.gray800, display: 'flex', alignItems: 'center', marginBottom: '1rem' }}><ThumbsUp style={{ marginRight: '0.5rem', color: COLORS.yellow500 }} size={20} /> Notes & Highlight Summary</h3>

                                    <textarea
                                        value={notes}
                                        onChange={(e) => setNotes(e.target.value)}
                                        rows={4}
                                        placeholder="Enter general notes about the job fit here..."
                                        style={{ width: '100%', padding: '0.75rem', border: '1px solid #d1d5db', borderRadius: '0.5rem', boxShadow: 'inset 0 2px 4px 0 rgba(0, 0, 0, 0.05)', fontSize: '0.875rem' }}
                                    ></textarea>

                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', paddingTop: '1rem', borderTop: '1px solid #e5e7eb' }}>
                                        <p style={{ fontSize: '0.875rem', fontWeight: 700, color: COLORS.gray700 }}>Saved Highlights ({highlights.length})</p>
                                        {highlights.map((h, index) => (
                                            <div key={index} className={`highlight-item ${h.type === 'like' ? 'highlight-like' : 'dislike'}`}>
                                                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                    {h.type === 'like' ? '👍' : '👎'} {h.text}
                                                </span>
                                                <button
                                                    onClick={() => removeHighlight(index)}
                                                    className="highlight-remove-btn"
                                                    title="Remove Highlight"
                                                >
                                                    <X size={12} />
                                                </button>
                                            </div>
                                        ))}
                                        {highlights.length === 0 && <p style={{ fontSize: '0.75rem', color: '#9ca3af', padding: '0.5rem', fontStyle: 'italic' }}>No phrases highlighted. **Select text** in the description to add a highlight.</p>}
                                    </div>
                                </div>

                                {/* Submission Button */}
                                <button
                                    onClick={handleSubmit}
                                    disabled={!job || submissionStatus === "Submitting..."}
                                    className="submit-button"
                                >
                                    {submissionStatus || `Submit Rating for Job ${job.job_id}`}
                                </button>

                                {submissionStatus && (
                                    <p style={{ textAlign: 'center', fontWeight: 700, fontSize: '1.125rem', transition: 'color 150ms ease-in-out', color: submissionStatus.includes("saved") ? COLORS.green600 : (submissionStatus.includes("Please rate") ? COLORS.yellow500 : COLORS.red600) }}>
                                        {submissionStatus}
                                    </p>
                                )}

                            </div>
                        </div>
                    </>
                )}
            </div>

            {/* Floating Menu Renderer (Renders when text is selected) */}
            {floatingMenu && (
                <FloatingMenu
                    x={floatingMenu.x}
                    y={floatingMenu.y}
                    onSelect={handleHighlightSelection}
                    menuRef={menuRef}
                />
            )}
        </div>
    );
}
