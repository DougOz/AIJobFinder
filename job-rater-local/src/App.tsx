import React, { useState, useEffect, useCallback, useRef } from 'react';

// --- CONFIGURATION ---
const API_BASE = 'http://localhost:5000/api';

// --- CONSTANTS ---
const RATING_MAP = {
    0: { label: 'Not Rated', color: 'text-gray-400', bg: 'bg-gray-100', text: 'Not Rated' },
    1: { label: 'Novice', color: 'text-red-600', bg: 'bg-red-50', text: 'Novice' },
    2: { label: 'Proficient', color: 'text-yellow-600', bg: 'bg-yellow-50', text: 'Proficient' },
    3: { label: 'Expert', color: 'text-green-600', bg: 'bg-green-50', text: 'Expert' },
};

// --- UTILITIES ---

const getOverallColor = (score) => {
    if (score === 0) return 'color-gray-400';
    if (score >= 1 && score <= 3) return 'color-red-600';
    if (score >= 4 && score <= 6) return 'color-yellow-600';
    if (score >= 7 && score <= 10) return 'color-green-600';
    return 'color-gray-800';
};

const formatScoreAsPercent = (score) => {
    return `${((score || 0) * 100).toFixed(1)}%`;
};

const renderDescriptionWithHighlights = (description, highlights) => {
    let contentHtml = description;

    if (!description) {
        return { __html: '<p class="color-red-600">Job description not available.</p>' };
    }

    highlights.forEach(highlight => {
        const escapedHighlight = highlight.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`(${escapedHighlight})`, 'g');
        contentHtml = contentHtml.replace(regex, '<span class="highlighted-text">$1</span>');
    });

    return { __html: contentHtml };
};

// --- ICON COMPONENTS (Simple SVG replacements) ---

const ChartBarIcon = ({ className }) => (
    <svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
        <path d="M4 22H2V11h2v11zM8 22H6V6h2v16zM12 22H10V2h2v20zM16 22H14V11h2v11zM20 22H18V6h2v16z" />
    </svg>
);

const CheckSquareIcon = ({ className }) => (
    <svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
        <path d="M18 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V4a2 2 0 00-2-2zM9 16.17l-3.59-3.59L4 14l5 5L20 8l-1.41-1.41z" />
    </svg>
);

const BookOpenIcon = ({ className }) => (
    <svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
        <path d="M21 21v-8a2 2 0 00-2-2h-3V7a2 2 0 00-2-2H8a2 2 0 00-2 2v4H3a2 2 0 00-2 2v8a2 2 0 002 2h16a2 2 0 002-2zM8 7h8v4H8V7z" />
    </svg>
);

const FloppyDiskIcon = ({ className }) => (
    <svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
        <path d="M19 2H5a2 2 0 00-2 2v16a2 2 0 002 2h14a2 2 0 002-2V4a2 2 0 00-2-2zM8 17H6v-3h2v3zM18 7h-6V4h6v3z" />
    </svg>
);

const MagicWandIcon = ({ className }) => (
    <svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
        <path d="M20.5 2L22 3.5l-1.5 1.5-1.5-1.5L20.5 2zM15 4l-1.5 1.5L15 7l1.5-1.5L15 4zM16 16l-4 4-2.5-2.5L14 14l2-2 2.5 2.5-4 4-2.5-2.5-2.5 2.5-4-4L6.5 9.5l4-4 2.5 2.5L16 12l2.5-2.5L22 14z" />
    </svg>
);

const ArrowLeftIcon = ({ className }) => (
    <svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
        <path d="M10 19l-7-7 7-7v4h11v6H10v4z" />
    </svg>
);

const ArrowRightIcon = ({ className }) => (
    <svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
        <path d="M14 5l7 7-7 7v-4H3v-6h11V5z" />
    </svg>
);

// --- MAIN APPLICATION COMPONENT ---
const App = () => {
    // New states for dynamic job loading and navigation
    const [jobIds, setJobIds] = useState([]);
    const [currentJobIndex, setCurrentJobIndex] = useState(0);

    const [jobData, setJobData] = useState({});
    const [ratedSkills, setRatedSkills] = useState([]);
    const [overallScore, setOverallScore] = useState(0);
    const [notes, setNotes] = useState('');
    const [highlights, setHighlights] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [message, setMessage] = useState(null);

    // Highlighting / Context Menu State
    const [contextMenuPos, setContextMenuPos] = useState(null);
    const contextMenuRef = useRef(null);
    const [currentSelection, setCurrentSelection] = useState('');

    const currentJobId = jobIds[currentJobIndex];
    const jobDetails = jobData.job_details || {};

    // --- SKILL COUNT CALCULATION ---
    const calculateSkillCounts = () => {
        const counts = { 'Expert': 0, 'Proficient': 0, 'Novice': 0, 'Not Rated': 0 };
        ratedSkills.forEach(skill => {
            const ratingLabel = RATING_MAP[skill.user_rating]?.text || 'Not Rated';
            counts[ratingLabel] = (counts[ratingLabel] || 0) + 1;
        });
        return counts;
    };
    const skillCounts = calculateSkillCounts();

    // --- API & DATA HANDLERS ---

    const showMessage = (title, content) => {
        setMessage({ title, content });
    };

    // 1. Fetch all job IDs (initial load)
    const fetchJobIds = useCallback(async () => {
        setIsLoading(true);
        try {
            // Assuming a new /jobs endpoint returns an array of job IDs
            const response = await fetch(`${API_BASE}/jobs`);

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP error! Status: ${response.status} fetching job list. Message: ${errorText.substring(0, 100)}...`);
            }
            const ids = await response.json();

            if (ids && ids.length > 0) {
                setJobIds(ids);
                // Start loading the details for the first job (index 0)
                setCurrentJobIndex(0);
            } else {
                showMessage('Info', 'No jobs found in the database. Please ensure the backend is populated.');
                setJobIds([]);
                setIsLoading(false);
            }
        } catch (error) {
            console.error('Error fetching job IDs:', error);
            showMessage('Error', `Could not load job list from the server. Ensure the backend is running and the /api/jobs route is correct. Error: ${error.message}`);
            setIsLoading(false);
        }
    }, []);


    // 2. Fetch details for the current job ID
    const fetchJobDetails = useCallback(async (jobIdToFetch) => {
        if (!jobIdToFetch) return;

        // Reset data while loading new job details
        setJobData({});
        setRatedSkills([]);
        setHighlights([]);
        setNotes('');
        setOverallScore(0);
        setIsLoading(true);

        try {
            const response = await fetch(`${API_BASE}/job/${jobIdToFetch}`);

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP error! Status: ${response.status}. Message: ${errorText.substring(0, 100)}...`);
            }
            const data = await response.json();

            setJobData(data);
            setRatedSkills(data.skill_proficiencies || []);
            setOverallScore(data.user_overall_score || 0);
            setNotes(data.user_notes || '');
            setHighlights(data.existing_highlights || []);
            //showMessage('Job Loaded', `Job ${currentJobIndex + 1} of ${jobIds.length} loaded successfully.`);

        } catch (error) {
            console.error('Error fetching job details:', error);
            showMessage('Error', `Failed to load details for job ${jobIdToFetch}. Error: ${error.message}`);
        } finally {
            setIsLoading(false);
        }
    }, [jobIds, currentJobIndex]); // Depends on jobIds and currentJobIndex for messaging and ID lookup

    // 3. Save the current rating
    const saveRating = async () => {
        if (isLoading || !currentJobId) return;
        setIsLoading(true);

        const payload = {
            job_id: currentJobId, // Use the current job ID
            overall_score: overallScore,
            notes: notes,
            highlights: highlights,
            rated_skills: ratedSkills,
            timestamp: new Date().toISOString()
        };

        try {
            const response = await fetch(`${API_BASE}/rate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP error! Status: ${response.status}. Message: ${errorText.substring(0, 100)}...`);
            }

            const result = await response.json();
            showMessage('Success', result.message);
        } catch (error) {
            console.error('Error saving rating:', error);
            showMessage('Error', `Failed to save rating. Check console for details. Error: ${error.message}`);
        } finally {
            setIsLoading(false);
        }
    };

    // --- NAVIGATION HANDLERS ---

    const goToNextJob = () => {
        if (currentJobIndex < jobIds.length - 1) {
            setCurrentJobIndex(prev => prev + 1);
        }
    };

    const goToPrevJob = () => {
        if (currentJobIndex > 0) {
            setCurrentJobIndex(prev => prev - 1);
        }
    };

    // --- EFFECTS ---

    // Effect 1: Initial load of all job IDs
    useEffect(() => {
        fetchJobIds();
    }, [fetchJobIds]);

    // Effect 2: Load job details whenever the current ID changes
    useEffect(() => {
        if (currentJobId) {
            fetchJobDetails(currentJobId);
        } else if (jobIds.length === 0 && !isLoading) {
            // Only show 'No Jobs' if we've attempted to load and found none
            showMessage('Notice', 'Job list is empty. Check backend connectivity and job data.');
        }
    }, [currentJobId, fetchJobDetails]);


    // --- CONTEXT MENU LOGIC (Omitted for brevity, kept in component) ---

    const handleContextMenu = useCallback((e) => {
        e.preventDefault();
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();
        if (selectedText.length > 0) {
            setCurrentSelection(selectedText);
            setContextMenuPos({ x: e.clientX, y: e.clientY });
        } else {
            setContextMenuPos(null);
        }
    }, []);

    const handleHighlightAction = useCallback(() => {
        if (currentSelection) {
            setHighlights(prev => {
                if (!prev.includes(currentSelection)) {
                    return [...prev, currentSelection];
                }
                return prev;
            });
        }
        setContextMenuPos(null);
        setCurrentSelection('');
    }, [currentSelection]);

    // Effect to hide context menu on click outside
    useEffect(() => {
        const handleClickOutside = (e) => {
            if (contextMenuRef.current && !contextMenuRef.current.contains(e.target)) {
                setContextMenuPos(null);
            }
        };
        const handleScroll = () => setContextMenuPos(null);
        document.addEventListener('mousedown', handleClickOutside);
        window.addEventListener('scroll', handleScroll);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
            window.removeEventListener('scroll', handleScroll);
        };
    }, []);


    // --- RENDERING COMPONENTS ---

    const SkillsList = () => (
        <div id="skills-list" className="space-y-2">
            {ratedSkills.length > 0 ? ratedSkills.map(skill => {
                const currentRating = skill.user_rating || 0;
                const ratingConfig = RATING_MAP[currentRating];

                const optionsHtml = Object.entries(RATING_MAP).map(([value, config]) =>
                    <option key={value} value={value}>{config.label}</option>
                );

                return (
                    <div key={skill.skill_name} className={`skill-row flex items-center justify-between text-sm p-2 rounded-lg ${ratingConfig.bg}`}>
                        <span className="font-medium color-gray-700 w-1/2 truncate">{skill.skill_name}</span>
                        <select
                            value={currentRating}
                            onChange={(e) => handleSkillChange(e, skill.skill_name)}
                            className={`skill-select p-1 text-xs border border-gray-300 rounded-lg focus-outline ${ratingConfig.color} font-semibold w-2/5 appearance-none cursor-pointer`}
                            style={{ borderColor: 'var(--color-gray-300)' }}
                        >
                            {optionsHtml}
                        </select>
                    </div>
                );
            }) : <p className="text-sm color-gray-400">No skills listed for this job.</p>}
        </div>
    );

    const SkillCountsSummary = () => (
        <div id="skill-counts" className="skill-counts-grid gap-3 text-center">
            {Object.entries(skillCounts).map(([label, count]) => {
                let color = 'bg-gray-100 color-gray-700';
                if (label === 'Expert') color = 'bg-green-100 color-green-700';
                else if (label === 'Proficient') color = 'bg-yellow-100 color-yellow-700';
                else if (label === 'Novice') color = 'bg-red-100 color-red-700';

                return (
                    <div key={label} className={`p-3 card-shadow-sm rounded-xl flex flex-col ${color}`}>
                        <span className="text-xl font-bold">{count}</span>
                        <span className="text-xs font-medium">{label}</span>
                    </div>
                );
            })}
        </div>
    );

    const HighlightsList = () => (
        <ul id="highlights-list" className="list-disc list-inside space-y-1 text-sm color-gray-600">
            {highlights.length === 0 ? (
                <li className="color-gray-400 list-none">No highlights saved yet. Right-click description text to add one.</li>
            ) : (
                highlights.map((h, index) => (
                    <li key={index} className="flex items-start justify-between">
                        <span className="font-semibold mr-2">{h}</span>
                        <button onClick={() => removeHighlight(h)} className="color-red-600 hover:color-red-800 text-xs flex-shrink-0 delete-btn" title="Remove Highlight">
                            🗑️
                        </button>
                    </li>
                ))
            )}
        </ul>
    );

    const handleOverallScoreChange = (e) => {
        setOverallScore(parseInt(e.target.value));
    };

    const handleSkillChange = (e, skillName) => {
        const newRating = parseInt(e.target.value);
        setRatedSkills(prevSkills =>
            prevSkills.map(s =>
                s.skill_name === skillName ? { ...s, user_rating: newRating } : s
            )
        );
    };

    const removeHighlight = useCallback((textToRemove) => {
        setHighlights(prevHighlights => prevHighlights.filter(h => h !== textToRemove));
    }, []);

    const isFirstJob = currentJobIndex === 0;
    const isLastJob = currentJobIndex === jobIds.length - 1;
    const totalJobs = jobIds.length;


    return (
        <div className="min-h-screen">
            <style>{`
                /* --- BASE & TYPOGRAPHY --- */
                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@100..900&display=swap');
                :root {
                    --color-indigo: #4f46e5;
                    --color-indigo-hover: #4338ca;
                    --color-gray-800: #1f2937;
                    --color-gray-700: #374151;
                    --color-gray-600: #4b5563;
                    --color-gray-500: #6b7280;
                    --color-gray-400: #9ca3af;
                    --color-gray-300: #d1d5db;
                    --color-gray-200: #e5e7eb;
                    --color-red-600: #dc2626;
                    --color-red-50: #fef2f2;
                    --color-red-800: #991b1b;
                    --color-yellow-600: #ca8a04;
                    --color-yellow-50: #fefce8;
                    --color-green-600: #059669;
                    --color-green-50: #ecfdf5;
                    --color-orange-500: #f97316;
                }

                body { 
                    font-family: 'Inter', sans-serif; 
                    background-color: #f7f7f9; 
                    margin: 0;
                }
                
                /* --- UTILITY CLASSES REPLACEMENT --- */

                .bg-white { background-color: #fff; }
                .shadow-lg { box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05); }
                .shadow-2xl { box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25); }
                .card-shadow-sm { box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05); }
                .rounded-xl { border-radius: 0.75rem; }
                .rounded-lg { border-radius: 0.5rem; }
                .rounded-md { border-radius: 0.375rem; }
                .min-h-screen { min-height: 100vh; }
                .sticky { position: sticky; }
                .top-0 { top: 0; }
                .z-50 { z-index: 50; }

                /* Spacing */
                .p-6 { padding: 1.5rem; } .p-5 { padding: 1.25rem; } .p-3 { padding: 0.75rem; }
                .py-3 { padding-top: 0.75rem; padding-bottom: 0.75rem; } .p-1 { padding: 0.25rem; }
                .pt-4 { padding-top: 1rem; } .mb-4 { margin-bottom: 1rem; }
                .mt-1 { margin-top: 0.25rem; } .mr-2 { margin-right: 0.5rem; } .mr-6 { margin-right: 1.5rem; }
                .px-4 { padding-left: 1rem; padding-right: 1rem; }

                .space-y-6 > * + * { margin-top: 1.5rem; }
                .space-y-4 > * + * { margin-top: 1rem; }
                .space-y-3 > * + * { margin-top: 0.75rem; }
                .space-y-2 > * + * { margin-top: 0.5rem; }
                .gap-6 { gap: 1.5rem; } .gap-3 { gap: 0.75rem; }

                /* Layout */
                .flex { display: flex; } .flex-col { flex-direction: column; }
                .items-center { align-items: center; } .items-start { align-items: flex-start; }
                .justify-between { justify-content: space-between; } .justify-center { justify-content: center; }
                .flex-shrink-0 { flex-shrink: 0; } .w-full { width: 100%; }
                .w-1\/2 { width: 50%; } .w-2\/5 { width: 40%; }
                .skill-counts-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
                .job-description-content { max-height: 60vh; overflow-y: auto; }
                .fixed { position: fixed; }
                .inset-0 { top: 0; right: 0; bottom: 0; left: 0; }
                .bg-black { background-color: rgba(0, 0, 0, 0.5); }
                .flex-grow { flex-grow: 1; }

                /* Colors (Foreground) */
                .color-gray-800 { color: var(--color-gray-800); } .color-gray-700 { color: var(--color-gray-700); }
                .color-gray-600 { color: var(--color-gray-600); } .color-gray-500 { color: var(--color-gray-500); }
                .color-gray-400 { color: var(--color-gray-400); } .color-red-600 { color: var(--color-red-600); }
                .hover\:color-red-800:hover { color: var(--color-red-800); } .color-yellow-600 { color: var(--color-yellow-600); }
                .color-green-600 { color: var(--color-green-600); } .color-indigo-600 { color: var(--color-indigo); }
                .text-white { color: white; }
                .text-indigo-500 { color: var(--color-indigo); }
                .text-green-500 { color: #10b981; } 
                .text-orange-500 { color: var(--color-orange-500); }
                .icon-base { width: 1.25rem; height: 1.25rem; margin-right: 0.5rem; }
                .icon-nav { width: 1rem; height: 1rem; }
                
                /* Colors (Background) */
                .bg-indigo-600 { background-color: var(--color-indigo); }
                .hover\:bg-indigo-700:hover { background-color: var(--color-indigo-hover); }
                .bg-gray-50 { background-color: #f9fafb; } .bg-gray-100 { background-color: #f3f4f6; }
                .bg-red-50 { background-color: var(--color-red-50); } .bg-yellow-50 { background-color: var(--color-yellow-50); }
                .bg-green-50 { background-color: var(--color-green-50); }
                .bg-green-100 { background-color: #dcfce7; } .bg-yellow-100 { background-color: #fef9c3; }
                .bg-red-100 { background-color: #fee2e2; }
                .disabled\:bg-indigo-400:disabled { background-color: #818cf8; cursor: not-allowed; }

                /* Text & Fonts */
                .text-xl { font-size: 1.25rem; } .text-2xl { font-size: 1.5rem; }
                .text-5xl { font-size: 3rem; line-height: 1; } .text-lg { font-size: 1.125rem; }
                .text-base { font-size: 1rem; } .text-sm { font-size: 0.875rem; } .text-xs { font-size: 0.75rem; }
                .font-bold { font-weight: 700; } .font-extrabold { font-weight: 800; }
                .font-semibold { font-weight: 600; } .font-medium { font-weight: 500; }
                .leading-relaxed { line-height: 1.625; } .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                .whitespace-pre-wrap { white-space: pre-wrap; }
                .list-disc { list-style-type: disc; } .list-inside { list-style-position: inside; } .list-none { list-style-type: none; }

                /* Form Controls */
                .border { border-width: 1px; border-style: solid; } .border-gray-300 { border-color: var(--color-gray-300); }
                .focus-outline:focus { box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.5); border-color: var(--color-indigo); }
                .appearance-none { appearance: none; } .cursor-pointer { cursor: pointer; } .cursor-text { cursor: text; }

                /* Custom Slider Style */
                input[type=range].w-full::-webkit-slider-thumb {
                    -webkit-appearance: none; height: 16px; width: 16px; border-radius: 50%;
                    background: var(--color-indigo); cursor: pointer; margin-top: -6px;
                }
                input[type=range].w-full::-moz-range-thumb {
                    height: 16px; width: 16px; border-radius: 50%;
                    background: var(--color-indigo); cursor: pointer;
                }
                .h-2 { height: 0.5rem; } .bg-gray-200 { background-color: var(--color-gray-200); }

                /* Custom Highlighting */
                .highlighted-text {
                    background-color: rgba(255, 235, 59, 0.5); 
                    border-radius: 4px; padding: 1px 3px; display: inline;
                }

                /* Context Menu */
                #custom-context-menu {
                    position: fixed; background-color: white; border-radius: 8px;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); z-index: 100; padding: 4px; min-width: 150px;
                }
                #custom-context-menu button {
                    display: flex; align-items: center; width: 100%; padding: 8px; border-radius: 6px;
                    transition: background-color 0.15s, color 0.15s;
                }
                #custom-context-menu button:hover {
                    background-color: #eef2ff; color: var(--color-indigo);
                }

                /* Responsive Grid */
                .main-grid {
                    display: grid; grid-template-columns: 1fr; gap: 1.5rem;
                    padding-bottom: 3rem; /* Extra space for mobile view */
                }
                @media (min-width: 1024px) { 
                    .main-grid {
                        grid-template-columns: 280px 1fr;
                        padding-bottom: 1.5rem;
                    }
                }
                .delete-btn { opacity: 0.7; transition: opacity 0.2s; }
                .delete-btn:hover { opacity: 1; }
            `}</style>

            {/* 1. FIXED HEADER */}
            <header className="sticky top-0 bg-white shadow-lg p-3 z-50">
                <div className="flex items-center justify-between">
                    <div className="flex-grow min-w-0">
                        <h1 className="text-xl font-bold color-gray-800 truncate">
                            Job Rater Pro: {jobDetails.title || (isLoading ? 'Loading Job...' : 'No Job Loaded')}
                        </h1>
                        <p className="text-sm color-gray-500 mt-1 truncate">
                            ID: {currentJobId || 'N/A'} | Location: {jobDetails.location || 'N/A'}
                        </p>
                    </div>

                    {/* Job Navigation Controls */}
                    <div className="flex items-center ml-4 flex-shrink-0">
                        <span className="text-sm font-medium color-gray-600 mr-3 hidden md:inline">
                            Job {totalJobs > 0 ? currentJobIndex + 1 : 0} of {totalJobs}
                        </span>

                        <button
                            onClick={goToPrevJob}
                            disabled={isFirstJob || totalJobs === 0 || isLoading}
                            className="bg-indigo-600 text-white p-2 rounded-lg hover:bg-indigo-700 disabled:bg-indigo-400 mr-2"
                            title="Previous Job"
                        >
                            <ArrowLeftIcon className="icon-nav" style={{ color: 'white' }} />
                        </button>
                        <button
                            onClick={goToNextJob}
                            disabled={isLastJob || totalJobs === 0 || isLoading}
                            className="bg-indigo-600 text-white p-2 rounded-lg hover:bg-indigo-700 disabled:bg-indigo-400"
                            title="Next Job"
                        >
                            <ArrowRightIcon className="icon-nav" style={{ color: 'white' }} />
                        </button>
                    </div>
                </div>
            </header>

            {/* MAIN CONTENT GRID */}
            <main className="main-grid p-6 pt-4">

                {/* LEFT COLUMN: Scores and Skills */}
                <div id="left-sidebar" className="space-y-6">

                    {/* Overall Match & Scores */}
                    <section className="bg-white p-5 rounded-xl shadow-lg">
                        <h2 className="text-lg font-semibold color-gray-700 mb-4 flex items-center">
                            <ChartBarIcon className="icon-base text-indigo-500" /> Match Scores
                        </h2>

                        <div className="space-y-3">
                            {/* Resume Match Score */}
                            <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                                <span className="text-sm font-medium color-gray-600">Resume Match</span>
                                <span className="text-base font-bold color-indigo-600">
                                    {formatScoreAsPercent(jobDetails.resume_score)}
                                </span>
                            </div>

                            {/* Semantic Score V2 */}
                            <div className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                                <span className="text-sm font-medium color-gray-600">Semantic Score V2</span>
                                <span className="text-base font-bold color-indigo-600">
                                    {formatScoreAsPercent(jobDetails.semantic_score_v2)}
                                </span>
                            </div>
                        </div>
                    </section>

                    {/* Skill Proficiency Summary */}
                    <section className="bg-white p-5 rounded-xl shadow-lg">
                        <h2 className="text-lg font-semibold color-gray-700 mb-4 flex items-center">
                            <CheckSquareIcon className="icon-base text-green-500" /> Skill Status
                        </h2>
                        <SkillCountsSummary />
                    </section>

                    {/* Skills Proficiency List */}
                    <section className="bg-white p-5 rounded-xl shadow-lg">
                        <h2 className="text-lg font-semibold color-gray-700 mb-4 flex items-center">
                            <BookOpenIcon className="icon-base text-orange-500" /> Required Skills
                        </h2>
                        {isLoading ? <p className="text-sm color-gray-400">Loading skills...</p> : <SkillsList />}
                    </section>
                </div>

                {/* RIGHT COLUMN: Job Description, Rating, Notes */}
                <div id="right-content" className="space-y-6">

                    {/* Overall Rating & Action */}
                    <section className="bg-white p-6 rounded-xl shadow-lg flex flex-col md:flex-row justify-between items-center">
                        <div className="mb-4 md:mb-0 md:mr-6">
                            <p className="text-sm font-medium color-gray-500">Overall Job Fit</p>
                            {/* Color-coded Score */}
                            <div className={`text-5xl font-extrabold transition-colors duration-300 ${getOverallColor(overallScore)}`}>
                                {overallScore}
                            </div>
                            <p className="text-xs font-semibold color-gray-400 mt-1">
                                {overallScore === 0 ? 'Not Rated' : 'Rated'}
                            </p>
                        </div>

                        {/* Rating Slider */}
                        <div className="w-full space-y-3">
                            <input
                                type="range"
                                id="overall-score-slider"
                                min="0"
                                max="10"
                                value={overallScore}
                                onChange={handleOverallScoreChange}
                                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
                            />
                            <div className="flex justify-between text-xs font-medium color-gray-500">
                                <span>0 (Not Rated)</span>
                                <span>10 (Perfect)</span>
                            </div>
                        </div>
                    </section>

                    {/* Job Description Area */}
                    <section className="bg-white p-6 rounded-xl shadow-lg">
                        <h2 className="text-2xl font-bold color-gray-800 mb-4">Job Description</h2>
                        {isLoading ? (
                            <div className="color-gray-400">Loading job description...</div>
                        ) : (
                            <div
                                id="job-description-content"
                                className="color-gray-700 leading-relaxed overflow-y-auto job-description-content relative cursor-text"
                                onContextMenu={handleContextMenu}
                                dangerouslySetInnerHTML={renderDescriptionWithHighlights(jobDetails.description, highlights)}
                            />
                        )}
                    </section>

                    {/* Notes and Highlights */}
                    <section className="bg-white p-6 rounded-xl shadow-lg space-y-6">
                        <h2 className="text-2xl font-bold color-gray-800">Your Notes & Highlights</h2>

                        {/* Highlights Display */}
                        <div>
                            <h3 className="text-lg font-semibold color-gray-700 mb-2">Saved Highlights</h3>
                            <HighlightsList />
                        </div>

                        {/* Notes Input */}
                        <div>
                            <h3 className="text-lg font-lg font-semibold color-gray-700 mb-2">Personal Notes</h3>
                            <textarea
                                id="notes-input"
                                rows="4"
                                className="w-full p-3 border border-gray-300 rounded-lg focus-outline"
                                placeholder="Add detailed thoughts about this job..."
                                value={notes}
                                onChange={(e) => setNotes(e.target.value)}
                                style={{ borderColor: 'var(--color-gray-300)' }}
                            />
                        </div>

                        {/* Save Button */}
                        <button
                            onClick={saveRating}
                            className="w-full py-3 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 shadow-lg flex items-center justify-center disabled:bg-indigo-400"
                            disabled={isLoading || !currentJobId}
                        >
                            <FloppyDiskIcon className="icon-base mr-2" style={{ color: 'white' }} />
                            {isLoading ? 'Saving...' : 'Save Rating and Skills'}
                        </button>
                    </section>
                </div>
            </main>

            {/* Custom Context Menu for Highlighting */}
            {contextMenuPos && (
                <div
                    ref={contextMenuRef}
                    id="custom-context-menu"
                    style={{ left: contextMenuPos.x, top: contextMenuPos.y }}
                >
                    <button
                        onClick={handleHighlightAction}
                    >
                        <MagicWandIcon className="icon-base" />
                        <span>Highlight Selection</span>
                    </button>
                </div>
            )}

            {/* Message Box/Modal for alerts */}
            {message && (
                <div className="fixed inset-0 bg-black flex items-center justify-center z-[100]">
                    <div className="bg-white p-6 rounded-xl shadow-2xl space-y-4" style={{ maxWidth: '400px', width: '90%' }}>
                        <h3 className={`text-lg font-bold ${message.title === 'Error' ? 'color-red-600' : 'color-gray-800'}`}>
                            {message.title}
                        </h3>
                        <p className="color-gray-600 whitespace-pre-wrap">{message.content}</p>
                        <button
                            onClick={() => setMessage(null)}
                            className="w-full py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
                        >
                            Close
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default App;
