import React, { useState, useEffect, useCallback, useRef } from 'react';

// --- CONFIGURATION ---
const API_BASE = 'http://localhost:5000/api';

// --- CONSTANTS ---
const RATING_MAP = {
    0: { label: 'Not Rated', textColor: '#6b7280', bgColor: '#f3f4f6', borderColor: '#d1d5db' },
    1: { label: 'Novice', textColor: '#b91c1c', bgColor: '#f7d7d7', borderColor: '#fca5a5' },
    2: { label: 'Proficient', textColor: '#a16207', bgColor: '#fef9c3', borderColor: '#facc15' },
    3: { label: 'Expert', textColor: '#046828', bgColor: '#9EFFC0', borderColor: '#34d399' },
};

const TITLE_RATING_MAP = {
    0: { label: 'N/R', color: '#6b7280', bgColor: '#f3f4f6' }, // Black/Gray
    1: { label: '✗', color: '#dc2626', bgColor: '#fee2e2' },   // Red X
    2: { label: '?', color: '#ca8a04', bgColor: '#fefce8' },   // Yellow ?
    3: { label: '✓', color: '#059669', bgColor: '#ecdfef5' },   // Green Check
};


// --- UTILITIES ---

const getOverallColor = (score) => {
    if (score === 0) return { color: '#9ca3af' }; // Gray for Not Rated
    const hue = (score - 1) * (120 / 9);
    return { color: `hsl(${hue}, 100%, 35%)` };
};

const formatScoreAsPercent = (score) => {
    return `${((score || 0) * 100).toFixed(1)}%`;
};

const formatDescription = (text) => {
    if (!text) return '<p>Job description not available.</p>';
    let processedText = text;
    const headingKeywords = [
        'Job Number:', 'The Opportunity:', 'You Have:', 'Nice If You Have:', 'Clearance:', 'Compensation', 'Identity Statement', 'Work Model', 'Commitment to Non-Discrimination',
        'Location:', 'Salary:', 'Description:', 'About the Role', 'Key Responsibilities', 'Minimum Qualifications', 'Work Flexibility', 'Contact:',
        'Required Skills & Experience', 'Desired Skills & Experience', 'What You Will Be Doing', 'The Offer', 'Pay & Benefits',
        'Overview', 'Responsibilities', 'Compensation and Benefits', 'Qualifications',
        'Company Overview', 'Group/Division', 'Job Description/Preferred Qualifications',
        'Job Description Summary', 'Job Description', 'Roles & Responsibilities', 'Desired Qualifications', 'Additional Information',
        'Position:', 'Duration:', 'Job ID:', 'Job Overview:', 'Pay Range:', 'About PTR Global',
        'Basic Qualifications', 'CLEARANCE REQUIREMENTS:', 'Responsibilities for this Position', 'What sets you apart:', 'Our Commitment to You:', 'Workplace Options:', 'Salary Note',
        'Who You Are:', 'The Work:', 'What We\'re Doing:', 'Who We Are:', 'Why Join Us:', 'EEO', 'Other Important Information', 'Work Schedule Information', 'National Pay Statement', 'Premium Pay Statement',
        'What’s in it for you:', 'What you get to do:', 'What you need to succeed:', 'Growth Opportunity', 'Work Arrangement', 'Visa Requirements',
        'Primary Responsibilities:', 'Why Join Data Intelligence, LLC?', 'About Us:', 'Job Summary', 'DUTIES AND RESPONSIBILITIES:', 'REQUIRED EXPERIENCE:', 'JOB QUALIFICATIONS:', 'APPLY TO:', 'START DATE:',
        'What you\'ll do', 'What experience you need', 'What could set you apart'
    ];
    const preHeadingRegex = new RegExp(`(${headingKeywords.join('|')})`, 'gi');
    processedText = processedText.replace(preHeadingRegex, '\n\n$1');
    processedText = processedText.replace(/([a-z\)\."])(?!NET|JS|VIEW|DB)([A-Z])/g, '$1\n$2');
    processedText = processedText.replace(/([a-zA-Z])(\d+\+?\s*years)/g, '$1\n$2');
    processedText = processedText.replace(/\s+([•*-])/g, '\n$1');
    processedText = processedText.replace(/(\. )([A-Z"'`])/g, '$1\n$2');
    const mainHeadingRegex = new RegExp(`^(${headingKeywords.join('|')}|Pay & Benefits|Benefits offered|Pay Rate|Combined Salary Range|Base Pay Range|Base Salary|Equity|Onsite Requirements|For U.S. based positions only|NOTE|Primary Location|Bonus Perks|Estimated Min Rate):?`, 'i');
    const subHeadingRegex = /^(Required skills|Preferred but not required|Bonus:|Tech Breakdown|Daily Responsibilities|Desired skills|Ideal Experience|Desired Skills)/i;
    const listItemRegex = /^\s*([•*-]|\d+\+?\s*years|Experience with|Proficiency in|Ability to|Solid experience|Strong knowledge|Strong understanding|Familiarity with|Hands-on|Bachelor's|Master's|Doctorate|Bonus based on|Paid time off|Medical Insurance|Dental Benefits|Vision Benefits|At least \d+ years)/i;
    const lines = processedText.split('\n');
    let html = '';
    let inList = false;
    for (const line of lines) {
        const trimmedLine = line.trim();
        if (trimmedLine === '' || trimmedLine.length < 2) continue;
        if (mainHeadingRegex.test(trimmedLine)) {
            if (inList) { html += '</ul>'; inList = false; }
            html += `<h3>${trimmedLine}</h3>`;
        } else if (subHeadingRegex.test(trimmedLine)) {
            if (inList) { html += '</ul>'; inList = false; }
            html += `<h4>${trimmedLine}</h4>`;
        } else if (listItemRegex.test(trimmedLine)) {
            if (!inList) { html += '<ul>'; inList = true; }
            html += `<li>${trimmedLine.replace(/^[•*-]\s*/, '')}</li>`;
        } else {
            if (inList) { html += '</ul>'; inList = false; }
            html += `<p>${trimmedLine}</p>`;
        }
    }
    if (inList) { html += '</ul>'; }
    html = html.replace(/<p>Employers have access/g, '</p><p class="footnote">Employers have access');
    html = html.replace(/Report this job/g, '</p><p class="footnote">Report this job');
    return html;
};


const renderDescriptionWithHighlights = (descriptionHtml, highlights) => {
    let contentHtml = descriptionHtml;
    if (!contentHtml) {
        return { __html: '<p class="color-red-600">Job description not available.</p>' };
    }
    highlights.forEach(highlight => {
        const escapedHighlight = highlight.text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`(${escapedHighlight})`, 'gi');
        const highlightClass = highlight.type === 'like' ? 'highlighted-like' : 'highlighted-dislike';
        contentHtml = contentHtml.replace(regex, `<span class="${highlightClass}">$1</span>`);
    });
    return { __html: contentHtml };
};


// --- ICON COMPONENTS ---
const ChartBarIcon = ({ className }) => (<svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M4 22H2V11h2v11zM8 22H6V6h2v16zM12 22H10V2h2v20zM16 22H14V11h2v11zM20 22H18V6h2v16z" /></svg>);
const CheckSquareIcon = ({ className }) => (<svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M18 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V4a2 2 0 00-2-2zM9 16.17l-3.59-3.59L4 14l5 5L20 8l-1.41-1.41z" /></svg>);
const BookOpenIcon = ({ className }) => (<svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M21 21v-8a2 2 0 00-2-2h-3V7a2 2 0 00-2-2H8a2 2 0 00-2 2v4H3a2 2 0 00-2 2v8a2 2 0 002 2h16a2 2 0 002-2zM8 7h8v4H8V7z" /></svg>);
const FloppyDiskIcon = ({ className }) => (<svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M19 2H5a2 2 0 00-2 2v16a2 2 0 002 2h14a2 2 0 002-2V4a2 2 0 00-2-2zM8 17H6v-3h2v3zM18 7h-6V4h6v3z" /></svg>);
const LinkIcon = ({ className }) => (<svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M10.586 13.414a1 1 0 01-1.414 1.414 5 5 0 01-7.07-7.071 1 1 0 011.414-1.414 3 3 0 004.242 4.242l1.414-1.414a1 1 0 011.414 1.414zm2.828-2.828a1 1 0 011.414-1.414 5 5 0 017.07 7.071 1 1 0 11-1.414 1.414 3 3 0 00-4.242-4.242l-1.414 1.414a1 1 0 01-1.414-1.414z" /></svg>);
const ThumbUpIcon = ({ className }) => (<svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M21 7h-6.31l.95-4.57.03-.32a1.5 1.5 0 00-1.5-1.5L12 2l-1.36 6.36L9 12v9h9l1.34-6.68L21 7zM3 12h4v9H3z" /></svg>);
const ThumbDownIcon = ({ className }) => (<svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M3 17h6.31l-.95 4.57-.03.32a1.5 1.5 0 001.5 1.5L12 22l1.36-6.36L15 12V3H6l-1.34 6.68L3 17zm18 0h-4V8h4v9z" /></svg>);
const ArrowLeftIcon = ({ className }) => (<svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M10 19l-7-7 7-7v4h11v6H10v4z" /></svg>);
const ArrowRightIcon = ({ className }) => (<svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M14 5l7 7-7 7v-4H3v-6h11V5z" /></svg>);
const EyeIcon = ({ className }) => (<svg className={className} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5C21.27 7.61 17 4.5 12 4.5zm0 13c-3.31 0-6-2.69-6-6s2.69-6 6-6 6 2.69 6 6-2.69 6-6 6zm0-10c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4z" /></svg>);


// --- MAIN APPLICATION COMPONENT ---
const App = () => {
    const [jobIds, setJobIds] = useState([]);
    const [currentJobIndex, setCurrentJobIndex] = useState(0);
    const [jobData, setJobData] = useState({});
    const [ratedSkills, setRatedSkills] = useState([]);
    const [overallScore, setOverallScore] = useState(0);
    const [notes, setNotes] = useState('');
    const [highlights, setHighlights] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [message, setMessage] = useState(null);
    const [contextMenuPos, setContextMenuPos] = useState(null);
    const contextMenuRef = useRef(null);
    const [currentSelection, setCurrentSelection] = useState('');
    const [titleRatings, setTitleRatings] = useState({});

    const [descriptionView, setDescriptionView] = useState('formatted');
    const [liveDescription, setLiveDescription] = useState({ html: null, error: null });
    const [isLiveDescLoading, setIsLiveDescLoading] = useState(false);

    // NEW: State for the job navigation input
    const [jobInputIndex, setJobInputIndex] = useState('');


    const currentJobId = jobIds[currentJobIndex];
    const jobDetails = jobData.job_details || {};

    const calculateSkillCounts = () => {
        const counts = { 'Expert': 0, 'Proficient': 0, 'Novice': 0, 'Not Rated': 0 };
        ratedSkills.forEach(skill => {
            const ratingLabel = RATING_MAP[skill.user_rating]?.label || 'Not Rated';
            counts[ratingLabel] = (counts[ratingLabel] || 0) + 1;
        });
        return counts;
    };
    const skillCounts = calculateSkillCounts();

    const showMessage = (title, content) => { setMessage({ title, content }); };

    const fetchJobIds = useCallback(async () => {
        setIsLoading(true);
        try {
            const response = await fetch(`${API_BASE}/jobs`);
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
            const ids = await response.json();
            if (ids && ids.length > 0) {
                setJobIds(ids);
                setCurrentJobIndex(0);
            } else {
                showMessage('Info', 'No jobs found.');
                setJobIds([]);
                setIsLoading(false);
            }
        } catch (error) {
            console.error('Error fetching job IDs:', error);
            showMessage('Error', `Could not load job list. ${error.message}`);
            setIsLoading(false);
        }
    }, []);

    const fetchJobDetails = useCallback(async (jobIdToFetch) => {
        if (!jobIdToFetch) return;
        setLiveDescription({ html: null, error: null });
        setDescriptionView('formatted');
        setJobData({}); setRatedSkills([]); setHighlights([]); setNotes(''); setOverallScore(0);
        setIsLoading(true);
        try {
            const response = await fetch(`${API_BASE}/job/${jobIdToFetch}`);
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}.`);
            const data = await response.json();
            setJobData(data);
            setRatedSkills(data.skill_proficiencies || []);
            setOverallScore(data.user_overall_score || 0);
            setNotes(data.user_notes || '');
            setHighlights(data.existing_highlights || []);
        } catch (error) {
            console.error('Error fetching job details:', error);
            showMessage('Error', `Failed to load details for job ${jobIdToFetch}. ${error.message}`);
        } finally {
            setIsLoading(false);
        }
    }, []);

    const saveRating = async () => {
        if (isLoading || !currentJobId) return;
        setIsLoading(true);
        const payload = {
            job_id: currentJobId, overall_score: overallScore, notes: notes,
            highlights: highlights, rated_skills: ratedSkills, timestamp: new Date().toISOString()
        };
        try {
            const response = await fetch(`${API_BASE}/rate`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
            });
            if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}.`);
            const result = await response.json();
            showMessage('Success', result.message);
        } catch (error) {
            console.error('Error saving rating:', error);
            showMessage('Error', `Failed to save rating. ${error.message}`);
        } finally {
            setIsLoading(false);
        }
    };

    const fetchTitleRatings = useCallback(async () => {
        try {
            const response = await fetch(`${API_BASE}/titles/ratings`);
            if (!response.ok) throw new Error('Failed to fetch title ratings');
            const data = await response.json();
            setTitleRatings(data);
        } catch (error) {
            console.error("Error fetching title ratings:", error);
            showMessage('Error', 'Could not load title ratings from the server.');
        }
    }, []);

    const saveTitleRating = async (title, rating) => {
        try {
            const response = await fetch(`${API_BASE}/titles/rate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, rating }),
            });
            if (!response.ok) throw new Error('Failed to save title rating');
            setTitleRatings(prev => ({ ...prev, [title]: rating }));
        } catch (error) {
            console.error("Error saving title rating:", error);
            showMessage('Error', 'Failed to save title rating.');
        }
    };

    const fetchLiveDescription = useCallback(async () => {
        if (!jobDetails.url) {
            showMessage('Error', 'This job does not have a URL to view.');
            return;
        }

        setIsLiveDescLoading(true);
        setLiveDescription({ html: null, error: null });

        try {
            const response = await fetch(`${API_BASE}/scrape-dice`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: jobDetails.url }),
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.error || `HTTP error! Status: ${response.status}`);
            }

            const data = await response.json();
            setLiveDescription({ html: data.html, error: null });
            setDescriptionView('live');

        } catch (error) {
            console.error("Error fetching live description:", error);
            setLiveDescription({ html: null, error: `Could not load live description. The page may no longer exist or the server may be down. (Error: ${error.message})` });
            setDescriptionView('live');
        } finally {
            setIsLiveDescLoading(false);
        }
    }, [jobDetails.url]);

    const goToNextJob = () => { if (currentJobIndex < jobIds.length - 1) setCurrentJobIndex(prev => prev + 1); };
    const goToPrevJob = () => { if (currentJobIndex > 0) setCurrentJobIndex(prev => prev - 1); };

    useEffect(() => {
        fetchJobIds();
        fetchTitleRatings();
    }, [fetchJobIds, fetchTitleRatings]);

    useEffect(() => {
        if (currentJobId) fetchJobDetails(currentJobId);
        else if (jobIds.length === 0 && !isLoading) showMessage('Notice', 'Job list is empty.');
    }, [currentJobId, fetchJobDetails]);

    // NEW: Effect to sync the input box with the current job index
    useEffect(() => {
        if (jobIds.length > 0) {
            setJobInputIndex((currentJobIndex + 1).toString());
        }
    }, [currentJobIndex, jobIds]);

    const handleContextMenu = useCallback((e) => {
        e.preventDefault();
        const selectedText = window.getSelection().toString().trim();
        if (selectedText.length > 0) {
            setCurrentSelection(selectedText);
            setContextMenuPos({ x: e.clientX, y: e.clientY });
        } else {
            setContextMenuPos(null);
        }
    }, []);

    const handleHighlightAction = useCallback((type) => {
        if (currentSelection) {
            setHighlights(prev => {
                const filtered = prev.filter(h => h.text !== currentSelection);
                return [...filtered, { text: currentSelection, type }];
            });
        }
        setContextMenuPos(null); setCurrentSelection('');
    }, [currentSelection]);

    useEffect(() => {
        const handleClickOutside = (e) => { if (contextMenuRef.current && !contextMenuRef.current.contains(e.target)) setContextMenuPos(null); };
        const handleScroll = () => setContextMenuPos(null);
        document.addEventListener('mousedown', handleClickOutside);
        window.addEventListener('scroll', handleScroll);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
            window.removeEventListener('scroll', handleScroll);
        };
    }, []);

    const handleOverallScoreChange = (e) => { setOverallScore(parseInt(e.target.value)); };
    const handleSkillChange = (e, skillName) => {
        const newRating = parseInt(e.target.value);
        setRatedSkills(prev => prev.map(s => s.skill_name === skillName ? { ...s, user_rating: newRating } : s));
    };
    const removeHighlight = useCallback((textToRemove) => {
        setHighlights(prev => prev.filter(h => h.text !== textToRemove));
    }, []);

    // NEW: Handler for navigating with the input box
    const handleJobNavigationInput = (e) => {
        if (e.key === 'Enter') {
            const newIndex = parseInt(jobInputIndex, 10) - 1;
            if (!isNaN(newIndex) && newIndex >= 0 && newIndex < jobIds.length) {
                setCurrentJobIndex(newIndex);
            } else {
                showMessage('Invalid Job Number', `Please enter a number between 1 and ${jobIds.length}.`);
                setJobInputIndex((currentJobIndex + 1).toString());
            }
        }
    };

    const isFirstJob = currentJobIndex === 0;
    const isLastJob = currentJobIndex === jobIds.length - 1;
    const totalJobs = jobIds.length;

    const SkillsList = () => (
        <div id="skills-list" className="space-y-1">
            {ratedSkills.length > 0 ? [...ratedSkills]
                .sort((a, b) => {
                    const ratingA = a.user_rating || 0;
                    const ratingB = b.user_rating || 0;
                    return ratingA - ratingB;
                })
                .map(skill => {
                    const ratingConfig = RATING_MAP[skill.user_rating || 0];
                    const skillRowStyle = { backgroundColor: ratingConfig.bgColor, borderColor: ratingConfig.borderColor };
                    const selectStyle = { color: ratingConfig.textColor, borderColor: ratingConfig.borderColor };
                    return (
                        <div key={skill.skill_name} className="skill-row flex items-center justify-between text-sm p-2 rounded-lg border" style={skillRowStyle}>
                            <span className="font-medium color-gray-700 w-1/2 truncate">{skill.skill_name}</span>
                            <select
                                value={skill.user_rating || 0}
                                onChange={(e) => handleSkillChange(e, skill.skill_name)}
                                className="skill-select py-1 px-2 text-xs border rounded-lg focus-outline font-semibold w-2/5 appearance-none cursor-pointer"
                                style={selectStyle}
                            >
                                {Object.entries(RATING_MAP).map(([val, conf]) => <option key={val} value={val}>{conf.label}</option>)}
                            </select>
                        </div>
                    );
                }) : <p className="text-sm color-gray-400">No skills listed.</p>}
        </div>
    );
    const SkillCountsSummary = () => {
        const orderedSkillLevels = [
            { label: 'Expert', config: RATING_MAP[3] },
            { label: 'Proficient', config: RATING_MAP[2] },
            { label: 'Novice', config: RATING_MAP[1] },
            { label: 'Not Rated', config: RATING_MAP[0] },
        ];

        return (
            <div id="skill-counts" className="space-y-2">
                {orderedSkillLevels.map(({ label, config }) => {
                    const count = skillCounts[label] || 0;
                    return (
                        <div key={label} className="p-2 card-shadow-sm rounded-lg flex items-center" style={{ backgroundColor: config.bgColor }}>
                            <span className="text-xl font-bold mr-2 w-8 text-right" style={{ color: config.textColor }}>{count}</span>
                            <span className="text-sm font-semibold" style={{ color: config.textColor }}>{label}</span>
                        </div>
                    );
                })}
            </div>
        );
    };
    const HighlightsList = () => (
        <ul id="highlights-list" className="list-disc list-inside space-y-1 text-sm color-gray-600">
            {highlights.length === 0 ? <li className="color-gray-400 list-none">No highlights saved.</li> : highlights.map((h, i) => (
                <li key={i} className="flex items-start justify-between">
                    <span className="font-semibold mr-2 flex items-center"><span className={`w-2 h-2 rounded-full mr-2 ${h.type === 'like' ? 'bg-green-500' : 'bg-red-500'}`}></span>{h.text}</span>
                    <button onClick={() => removeHighlight(h.text)} className="color-red-600 hover:color-red-800 text-xs flex-shrink-0 delete-btn" title="Remove">🗑️</button>
                </li>
            ))}
        </ul>
    );

    return (
        <div className="min-h-screen">
            <style>{`
                /* --- BASE & TYPOGRAPHY --- */
                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@100..900&display=swap');
                :root {
                    --color-indigo: #4f46e5; --color-indigo-hover: #4338ca; --color-gray-800: #1f2937;
                    --color-gray-700: #374151; --color-gray-600: #4b5563; --color-gray-500: #6b7280;
                    --color-gray-400: #9ca3af; --color-gray-300: #d1d5db; --color-gray-200: #e5e7eb;
                    --color-red-600: #dc2626; --color-red-800: #991b1b;
                    --color-yellow-600: #ca8a04; --color-green-600: #059669; --color-orange-500: #f97316;
                }
                body { font-family: 'Inter', sans-serif; background-color: #f9fafb; margin: 0; }
                
                /* --- HEADER FIX --- */
                header.app-header {
                    background-color: #ddd;
                    border-bottom: 1px solid var(--color-gray-200);
                }

                /* --- UTILITIES --- */
                .shadow-md { box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -2px rgba(0,0,0,0.1); }
                .rounded-xl { border-radius: 0.75rem; } .rounded-lg { border-radius: 0.5rem; } .min-h-screen { min-height: 100vh; }
                .sticky { position: sticky; } .top-0 { top: 0; } .z-50 { z-index: 50; }
                .p-6 { padding: 1.5rem; } .p-4 { padding: 1rem; } .p-3 { padding: 0.75rem; } .p-2 { padding: 0.5rem; }
                .pt-2 { padding-top: 0.5rem; } .mt-1 { margin-top: 0.25rem; } .mt-2 { margin-top: 0.5rem; }
                .mr-2 { margin-right: 0.5rem; } .mr-3 { margin-right: 0.75rem; } .mr-4 { margin-right: 1rem; } .ml-4 { margin-left: 1rem; } .mx-2 { margin-left: 0.5rem; margin-right: 0.5rem; }
                .mx-4 { margin-left: 1rem; margin-right: 1rem; } 
                .space-y-4 > * + * { margin-top: 1rem; } .space-y-2 > * + * { margin-top: 0.5rem; } .space-y-1 > * + * { margin-top: 0.25rem; }
                .flex { display: flex; } .flex-col { flex-direction: column; } .items-center { align-items: center; } .justify-between { justify-content: space-between; } .justify-center { justify-content: center; }
                .flex-shrink-0 { flex-shrink: 0; } .flex-grow { flex-grow: 1; } .w-full { width: 100%; } .self-center { align-self: center; }
                .py-1 { padding-top: 0.25rem; padding-bottom: 0.25rem; }
                .px-2 { padding-left: 0.5rem; padding-right: 0.5rem; }
                .border { border-width: 1px; } .border-b { border-bottom-width: 1px; } .border-gray-300 { border-color: var(--color-gray-300); } .border-none { border: none; }
                
                /* Description Formatting */
                .job-description-content h3 { font-size: 1.25rem; font-weight: 700; color: var(--color-gray-800); margin-top: 1.75rem; margin-bottom: 1rem; border-bottom: 1px solid var(--color-gray-200); padding-bottom: 0.5rem; }
                .job-description-content h4 { font-size: 1.1rem; font-weight: 600; color: var(--color-gray-700); margin-top: 1.5rem; margin-bottom: 0.75rem; }
                .job-description-content p { margin-bottom: 1rem; }
                .job-description-content ul { list-style: disc; padding-left: 20px; margin-bottom: 1rem; }
                .job-description-content li { margin-bottom: 0.5rem; padding-left: 0.5rem; }
                .job-description-content .footnote { font-size: 0.75rem; color: var(--color-gray-500); margin-top: 1.5rem; }

                .fixed { position: fixed; } .inset-0 { top: 0; right: 0; bottom: 0; left: 0; }
                .bg-black { background-color: rgba(0, 0, 0, 0.5); } .bg-white { background-color: white; }
                .color-gray-800 { color: var(--color-gray-800); } .color-gray-700 { color: var(--color-gray-700); }
                .color-gray-500 { color: var(--color-gray-500); } .color-gray-400 { color: var(--color-gray-400); }
                .color-indigo-600 { color: var(--color-indigo); } .text-white { color: white; } .text-red-600 { color: #dc2626; } .text-green-700 { color: #047857; }
                .icon-base { width: 1.25rem; height: 1.25rem; margin-right: 0.5rem; } 
                .icon-nav { width: 1rem; height: 1rem; } 
                .icon-xs { width: 0.75rem; height: 0.75rem; margin-right: 0.25rem; }
                .bg-indigo-600 { background-color: var(--color-indigo); } .hover\\:bg-indigo-700:hover { background-color: var(--color-indigo-hover); }
                .bg-green-500 { background-color: #22c55e; } .bg-red-500 { background-color: #ef4444; }
                .disabled\\:bg-indigo-400:disabled { background-color: #818cf8; cursor: not-allowed; opacity: 0.7; }
                .text-xl { font-size: 1.25rem; } .text-lg { font-size: 1.125rem; } .text-sm { font-size: 0.875rem; } .text-xs { font-size: 0.75rem; } .text-2xl { font-size: 1.5rem; } .text-5xl { font-size: 3rem; line-height: 1; }
                .font-bold { font-weight: 700; } .font-semibold { font-weight: 600; } .font-extrabold { font-weight: 800; }
                .leading-relaxed { line-height: 1.625; } .truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                .focus-outline:focus { box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.5); }
                .appearance-none { appearance: none; } .cursor-pointer { cursor: pointer; }
                .highlighted-like { background-color: rgba(34, 197, 94, 0.3); } .highlighted-dislike { background-color: rgba(239, 68, 68, 0.3); }
                #custom-context-menu { position: fixed; background-color: white; border-radius: 8px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15); z-index: 100; padding: 4px; min-width: 150px; }
                #custom-context-menu button { display: flex; align-items: center; width: 100%; text-align: left; padding: 8px; border-radius: 6px; }
                #custom-context-menu button:hover { background-color: #eef2ff; }
                .main-grid { display: grid; grid-template-columns: 1fr; gap: 1rem; }
                @media (min-width: 1024px) { .main-grid { grid-template-columns: 280px 1fr; } }
                .delete-btn { opacity: 0.7; } .delete-btn:hover { opacity: 1; }
                input[type=range].header-slider::-webkit-slider-thumb { -webkit-appearance: none; height: 1rem; width: 1rem; border-radius: 50%; background: var(--color-indigo); cursor: pointer; margin-top: -3px; }
                .w-12 { width: 3rem; } .mx-1 { margin-left: 0.25rem; margin-right: 0.25rem; } .text-center { text-align: center; }
            `}</style>

            <header className="sticky top-0 app-header shadow-md p-2 z-50">
                <div className="flex items-center justify-between">
                    <div className="flex items-center flex-grow min-w-0" style={{ flexBasis: '50%' }}>
                        {jobDetails.title && (
                            <select
                                value={titleRatings[jobDetails.title] || 0}
                                onChange={(e) => saveTitleRating(jobDetails.title, parseInt(e.target.value))}
                                className="p-2 text-xl border-none rounded-lg focus-outline font-bold appearance-none cursor-pointer mr-4"
                                style={{
                                    color: TITLE_RATING_MAP[titleRatings[jobDetails.title] || 0].color,
                                    backgroundColor: TITLE_RATING_MAP[titleRatings[jobDetails.title] || 0].bgColor,
                                    width: '65px',
                                    textAlign: 'center'
                                }}
                            >
                                {Object.entries(TITLE_RATING_MAP).map(([value, config]) =>
                                    <option key={value} value={value} style={{ color: config.color, backgroundColor: 'white', fontWeight: 'bold' }}>{config.label}</option>
                                )}
                            </select>
                        )}
                        <div>
                            <h1 className="text-xl font-bold color-gray-800 truncate">{jobDetails.title || 'Loading...'}</h1>
                            <div className="flex items-center text-sm color-gray-500 mt-1 truncate">
                                <span>{jobDetails.company || 'N/A'}</span>
                                {jobDetails.url && (
                                    <><span className="mx-2">|</span><a href={jobDetails.url} target="_blank" rel="noopener noreferrer" className="flex items-center color-indigo-600 hover:underline"><LinkIcon className="icon-xs mr-2" /> View Listing</a></>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center justify-center flex-grow mx-4">
                        <div className="flex flex-col items-center">
                            <div className="text-5xl font-extrabold" style={getOverallColor(overallScore)}>{overallScore}</div>
                            <p className="text-xs font-semibold color-gray-400 mt-1">Job Fit</p>
                            <input type="range" min="0" max="10" value={overallScore} onChange={handleOverallScoreChange} className="w-full header-slider h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer mt-2" style={{ maxWidth: '150px' }} />
                        </div>
                        <button onClick={saveRating} disabled={isLoading || !currentJobId} className="bg-indigo-600 text-white p-2 rounded-lg hover:bg-indigo-700 disabled:bg-indigo-400 ml-4 flex-shrink-0 self-center" title="Save Rating">
                            <FloppyDiskIcon className="icon-nav" />
                        </button>
                    </div>

                    <div className="flex items-center flex-shrink-0">
                        <span className="text-sm font-medium color-gray-600 mr-4 hidden md:inline flex items-center">
                            Job&nbsp;
                            <input
                                type="text"
                                value={jobInputIndex}
                                onChange={(e) => setJobInputIndex(e.target.value)}
                                onKeyDown={handleJobNavigationInput}
                                className="w-12 text-center font-semibold rounded border border-gray-300 mx-1"
                            />
                            &nbsp;of {totalJobs}
                        </span>
                        <button onClick={goToPrevJob} disabled={isFirstJob || isLoading} className="bg-indigo-600 text-white p-2 rounded-lg hover:bg-indigo-700 disabled:bg-indigo-400 mr-2" title="Previous Job"><ArrowLeftIcon className="icon-nav" /></button>
                        <button onClick={goToNextJob} disabled={isLastJob || isLoading} className="bg-indigo-600 text-white p-2 rounded-lg hover:bg-indigo-700 disabled:bg-indigo-400" title="Next Job"><ArrowRightIcon className="icon-nav" /></button>
                    </div>
                </div>
            </header>

            <main className="main-grid p-4 pt-2">
                <div id="left-sidebar" className="space-y-4">
                    <section className="bg-white p-4 rounded-xl shadow-lg">
                        <h2 className="text-lg font-semibold color-gray-700 mb-3 flex items-center"><ChartBarIcon className="icon-base mr-2 text-indigo-500" /> Match Scores</h2>
                        <div className="space-y-2">
                            <div className="flex justify-between items-center p-2 bg-gray-100 rounded-lg"><span className="text-sm font-medium color-gray-600">Resume Match</span><span className="text-base font-bold color-indigo-600">{formatScoreAsPercent(jobDetails.resume_score)}</span></div>
                            <div className="flex justify-between items-center p-2 bg-gray-100 rounded-lg"><span className="text-sm font-medium color-gray-600">Semantic Score V2</span><span className="text-base font-bold color-indigo-600">{formatScoreAsPercent(jobDetails.semantic_score_v2)}</span></div>
                        </div>
                    </section>
                    <section className="bg-white p-4 rounded-xl shadow-lg">
                        <h2 className="text-lg font-semibold color-gray-700 mb-3 flex items-center"><CheckSquareIcon className="icon-base mr-2 text-green-500" /> Skill Status</h2>
                        <SkillCountsSummary />
                    </section>
                    <section className="bg-white p-4 rounded-xl shadow-lg">
                        <h2 className="text-lg font-semibold color-gray-700 mb-3 flex items-center"><BookOpenIcon className="icon-base mr-2 text-orange-500" /> Skills</h2>
                        {isLoading ? <p className="text-sm color-gray-400">Loading...</p> : <SkillsList />}
                    </section>
                </div>
                <div id="right-content" className="space-y-4">
                    <section className="bg-white p-6 rounded-xl shadow-lg">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-2xl font-bold color-gray-800">Job Description</h2>
                            {jobDetails.url && (
                                <button
                                    onClick={() => {
                                        if (descriptionView === 'formatted') {
                                            fetchLiveDescription();
                                        } else {
                                            setDescriptionView('formatted');
                                        }
                                    }}
                                    className="bg-indigo-100 text-indigo-700 px-3 py-1 rounded-lg text-sm font-semibold hover:bg-indigo-200"
                                    disabled={isLiveDescLoading}
                                >
                                    <EyeIcon className="icon-xs mr-2" />
                                    {isLiveDescLoading ? 'Loading...' : (descriptionView === 'formatted' ? 'View Live' : 'View Formatted')}
                                </button>
                            )}
                        </div>

                        {isLoading ? (
                            <div className="color-gray-400">Loading...</div>
                        ) : (
                            descriptionView === 'live' ? (
                                isLiveDescLoading ? (
                                    <div className="color-gray-400">Fetching live description from Dice.com...</div>
                                ) : (
                                    liveDescription.error ? (
                                        <div className="text-red-600 p-4 bg-red-50 rounded-lg">{liveDescription.error}</div>
                                    ) : (
                                        <div id="live-job-description" dangerouslySetInnerHTML={{ __html: liveDescription.html }} onContextMenu={handleContextMenu} />
                                    )
                                )
                            ) : (
                                <div
                                    id="job-description-content"
                                    className="color-gray-700 leading-relaxed"
                                    onContextMenu={handleContextMenu}
                                    dangerouslySetInnerHTML={renderDescriptionWithHighlights(formatDescription(jobDetails.description), highlights)}
                                />
                            )
                        )}
                    </section>
                    <section className="bg-white p-6 rounded-xl shadow-lg space-y-4">
                        <h2 className="text-2xl font-bold color-gray-800">Your Notes & Highlights</h2>
                        <div><h3 className="text-lg font-semibold color-gray-700 mb-2">Saved Highlights</h3><HighlightsList /></div>
                        <div><h3 className="text-lg font-semibold color-gray-700 mb-2">Personal Notes</h3><textarea id="notes-input" rows="4" className="w-full p-3 border border-gray-300 rounded-lg focus-outline" placeholder="Add thoughts..." value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
                        <button onClick={saveRating} className="w-full py-3 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 shadow-lg flex items-center justify-center disabled:bg-indigo-400" disabled={isLoading || !currentJobId}><FloppyDiskIcon className="icon-base mr-2" />{isLoading ? 'Saving...' : 'Save Rating and Skills'}</button>
                    </section>
                </div>
            </main>

            {contextMenuPos && (
                <div ref={contextMenuRef} id="custom-context-menu" style={{ left: contextMenuPos.x, top: contextMenuPos.y }}>
                    <button onClick={() => handleHighlightAction('like')} className="color-green-700"><ThumbUpIcon className="icon-base mr-2" /><span>Like (Green)</span></button>
                    <button onClick={() => handleHighlightAction('dislike')} className="color-red-700"><ThumbDownIcon className="icon-base mr-2" /><span>Dislike (Red)</span></button>
                </div>
            )}

            {message && (
                <div className="fixed inset-0 bg-black bg-white flex items-center justify-center z-[100]">
                    <div className="bg-white p-6 rounded-xl shadow-2xl space-y-4" style={{ maxWidth: '400px', width: '90%' }}>
                        <h3 className={`text-lg font-bold ${message.title === 'Error' ? 'color-red-600' : 'color-gray-800'}`}>{message.title}</h3>
                        <p className="color-gray-600 whitespace-pre-wrap">{message.content}</p>
                        <button onClick={() => setMessage(null)} className="w-full py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">Close</button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default App;

