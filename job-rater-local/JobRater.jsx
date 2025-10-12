import React, { useState, useEffect, useCallback, useMemo } from 'react';
// FIX: Swapped react-icons/sl for standard lucide-react icons
import { Pencil, FileText, CheckCircle, ChevronRight, ChevronLeft } from 'lucide-react';

// Configuration
const API_BASE_URL = 'http://localhost:5000/api';
const JOB_ID_TO_FETCH = '123'; // Static job ID for demo
const DEFAULT_PROFILE_NAME = 'Doug'; // Matches the server's expected profile

// Utility to determine color based on proficiency rating (1, 2, 3)
const getSkillColor = (rating) => {
    if (rating === 1) return 'bg-red-400 text-red-900 ring-red-600/50';
    if (rating === 2) return 'bg-yellow-400 text-yellow-900 ring-yellow-600/50';
    if (rating === 3) return 'bg-green-400 text-green-900 ring-green-600/50';
    if (rating >= 4) return 'bg-blue-200 text-blue-800 ring-blue-600/50';
    return 'bg-gray-200 text-gray-700 ring-gray-400/50';
};

// --- Main App Component ---
export default function App() {
    const [job, setJob] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [overallScore, setOverallScore] = useState(5);
    const [notes, setNotes] = useState('');
    const [submissionStatus, setSubmissionStatus] = useState(null);
    const [skillProficiencies, setSkillProficiencies] = useState({}); // {skillName: rating, ...}
    const [source, setSource] = useState('');

    // 1. Data Fetching Effect
    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            setError(null);
            try {
                const response = await fetch(`${API_BASE_URL}/job/${JOB_ID_TO_FETCH}`);
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                const data = await response.json();

                if (data.error) {
                    throw new Error(data.error);
                }

                setJob(data.job_details);
                setSource(data.source);

                // Convert array of proficiencies into a map for easy lookup
                const profMap = data.skill_proficiencies.reduce((acc, curr) => {
                    acc[curr.skill_name] = curr.user_rating;
                    return acc;
                }, {});
                setSkillProficiencies(profMap);

            } catch (err) {
                console.error("Fetch error:", err);
                setError(`Failed to connect to local server (${API_BASE_URL}). Please ensure 'job_rater_server.py' is running. Error: ${err.message}`);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []); // Run only once on mount

    // 2. Identify skills relevant to the job and merge with proficiency
    const relevantSkills = useMemo(() => {
        if (!job) return [];

        // Merge job skills with current proficiency ratings
        return job.skills.map(skillName => ({
            name: skillName,
            currentRating: skillProficiencies[skillName] || 0, // Default to 0 if no score
        })).sort((a, b) => b.currentRating - a.currentRating); // Sort by rating descending
    }, [job, skillProficiencies]);

    // 3. Highlight/Notes Logic
    const handleDescriptionSelection = (event) => {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();
        if (selectedText.length > 3) {
            const newNote = `\n--- Selected Phrase ---\n"${selectedText}" (Likely positive/negative)\n-----------------------`;
            setNotes(prevNotes => (prevNotes.includes(newNote) ? prevNotes : prevNotes + newNote));
            selection.removeAllRanges();
        }
    };

    // 4. Individual Skill Update Logic
    const handleSkillUpdate = useCallback((skillName, newRating) => {
        setSkillProficiencies(prev => ({
            ...prev,
            [skillName]: newRating,
        }));
    }, []);

    // 5. Submission Logic
    const handleSubmit = async () => {
        if (!job) return;

        setSubmissionStatus("Submitting...");

        const submissionData = {
            job_id: JOB_ID_TO_FETCH,
            profile_id: DEFAULT_PROFILE_NAME,
            overall_score: overallScore,
            notes: notes,
            // Only send the skills present in the current job posting and their updated ratings
            rated_skills: relevantSkills.map(s => ({
                skill_name: s.name,
                user_rating: skillProficiencies[s.name] || 0 // Use the latest state
            })),
            source: source
        };

        try {
            const response = await fetch(`${API_BASE_URL}/rate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(submissionData),
            });

            if (!response.ok) {
                throw new Error(`Submission failed with status: ${response.status}`);
            }

            setSubmissionStatus("Rating saved successfully!");
            setTimeout(() => setSubmissionStatus(null), 3000);

            // Reset interface (optional, but good practice)
            // setOverallScore(5);
            // setNotes('');

        } catch (err) {
            console.error("Submission error:", err);
            setSubmissionStatus(`Error saving rating: ${err.message}`);
            setTimeout(() => setSubmissionStatus(null), 5000);
        }
    };

    // --- Render Logic ---
    if (loading) {
        return (
            <div className="flex items-center justify-center h-screen bg-gray-50">
                <div className="text-xl text-indigo-600 animate-pulse">
                    Connecting to local server...
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="p-8 bg-red-100 border-l-4 border-red-500 text-red-700 font-mono">
                <h2 className="text-lg font-bold mb-2">Connection Error</h2>
                <p>{error}</p>
                <p className="mt-4 text-sm">Action required: Please start your Flask server using the command: <code className="bg-red-200 p-1 rounded">python job_rater_server.py</code></p>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 font-inter p-4 sm:p-8">
            <script src="https://cdn.tailwindcss.com"></script>
            <div className="max-w-6xl mx-auto bg-white shadow-xl rounded-xl p-6 sm:p-10">

                <header className="mb-8 border-b pb-4">
                    <p className="text-sm text-gray-500 mb-1">Source: {source} (Job ID: {JOB_ID_TO_FETCH})</p>
                    <h1 className="text-3xl sm:text-4xl font-extrabold text-gray-900 mb-1 leading-tight">{job?.title}</h1>
                    <p className="text-xl font-medium text-indigo-600">{job?.company} — <span className="text-gray-500 font-normal">{job?.location}</span></p>
                </header>

                {/* Layout: Job Details (Left) and Rating Controls (Right) */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">

                    {/* LEFT COLUMN: Job Details & Description */}
                    <div className="lg:col-span-2 space-y-8">

                        {/* Metadata Section */}
                        <div className="bg-indigo-50 p-6 rounded-lg">
                            <h2 className="text-xl font-semibold text-indigo-800 mb-4 flex items-center">Job Overview</h2>
                            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm text-gray-700">
                                <div><dt className="font-medium text-gray-500">Posted Date:</dt><dd>{job?.posted_date}</dd></div>
                                <div><dt className="font-medium text-gray-500">Job Type:</dt><dd className="capitalize">{job?.job_types.join(', ')}</dd></div>
                                <div><dt className="font-medium text-gray-500">Salary Range:</dt><dd className="font-semibold">{job?.salary || 'Not specified'}</dd></div>
                                <div><dt className="font-medium text-gray-500">Resume Match Score:</dt><dd>{(job?.resume_score * 100).toFixed(1)}%</dd></div>
                            </dl>
                        </div>

                        {/* Description Section */}
                        <div>
                            <h2 className="text-2xl font-semibold text-gray-800 mb-4 flex items-center"><FileText className="mr-2" size={20} /> Job Description</h2>
                            <div
                                className="prose max-w-none text-gray-700 border p-4 rounded-lg bg-white shadow-inner cursor-pointer"
                                onMouseUp={handleDescriptionSelection}
                            >
                                <p className="text-sm text-indigo-600 font-medium mb-3">
                                    Click and drag your mouse to select important phrases. Selected text will be copied to your Notes.
                                </p>
                                {/* Display description as paragraphs */}
                                {(job?.description || "No description provided.").split('\n').map((paragraph, index) => (
                                    <p key={index} className="mb-2">{paragraph}</p>
                                ))}
                            </div>
                        </div>

                    </div>

                    {/* RIGHT COLUMN: Rating & Skills Control */}
                    <div className="lg:col-span-1 space-y-8">

                        {/* 1. Overall Match Score (1-10) */}
                        <div className="bg-gray-50 p-6 rounded-lg shadow-md">
                            <h2 className="text-2xl font-bold text-gray-800 mb-4 flex items-center"><CheckCircle className="mr-2 text-green-600" size={20} /> Overall Match Score (1-10)</h2>
                            <p className="text-sm text-gray-600 mb-4">How well does this job match your **skills, preferences, and career goals**?</p>

                            <div className="flex justify-between items-center mb-2">
                                <span className="text-xl font-bold text-indigo-600">{overallScore}</span>
                                <span className="text-sm text-gray-500">1 (Poor) to 10 (Perfect)</span>
                            </div>

                            <input
                                type="range"
                                min="1"
                                max="10"
                                step="1"
                                value={overallScore}
                                onChange={(e) => setOverallScore(parseInt(e.target.value))}
                                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer range-lg"
                                style={{ accentColor: '#4f46e5' }}
                            />
                        </div>

                        {/* 2. Skills Proficiency Review */}
                        <div className="p-6 rounded-lg bg-white border shadow-md">
                            <h2 className="text-2xl font-semibold text-gray-800 mb-4 flex items-center"><Pencil className="mr-2" size={20} /> Skill Ratings & Update</h2>
                            <p className="text-sm text-gray-600 mb-4">
                                Your current proficiency in skills relevant to this job.
                                <span className="font-bold">Color-coded</span> ratings (1-3) are from your `skills_proficiency` collection.
                            </p>

                            <div className="space-y-3">
                                {relevantSkills.map(skill => (
                                    <div key={skill.name} className="flex items-center justify-between p-3 rounded-lg ring-1 transition-all duration-150 ease-in-out"
                                        // Apply color based on current rating
                                        // FIX #5: Color code skills based on rating (1, 2, 3)
                                        style={{
                                            borderColor: skill.currentRating >= 1 && skill.currentRating <= 3 ? (skill.currentRating === 1 ? '#ef4444' : skill.currentRating === 2 ? '#f59e0b' : '#10b981') : '#d1d5db',
                                            backgroundColor: skill.currentRating >= 1 && skill.currentRating <= 3 ? (skill.currentRating === 1 ? '#fee2e2' : skill.currentRating === 2 ? '#fffbeb' : '#e0f2f1') : '#f9fafb'
                                        }}
                                    >
                                        <span className="font-medium text-gray-900">{skill.name}</span>

                                        {/* FIX #6: Update individual skill score */}
                                        <div className="flex items-center space-x-2">
                                            <button
                                                onClick={() => handleSkillUpdate(skill.name, Math.max(0, skillProficiencies[skill.name] - 1))}
                                                className="p-1.5 text-gray-500 hover:text-indigo-600 rounded-full hover:bg-indigo-100 transition"
                                            >
                                                <ChevronLeft size={14} />
                                            </button>

                                            <span className={`px-3 py-1 text-xs font-semibold rounded-full ring-2 ${getSkillColor(skillProficiencies[skill.name] || 0)} min-w-[3rem] text-center`}>
                                                {skillProficiencies[skill.name] || 0}
                                            </span>

                                            <button
                                                onClick={() => handleSkillUpdate(skill.name, Math.min(10, (skillProficiencies[skill.name] || 0) + 1))}
                                                className="p-1.5 text-gray-500 hover:text-indigo-600 rounded-full hover:bg-indigo-100 transition"
                                            >
                                                <ChevronRight size={14} />
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* 3. Notes Field */}
                        <div>
                            <h2 className="text-2xl font-semibold text-gray-800 mb-4 flex items-center"><FileText className="mr-2" size={20} /> Notes & Highlighting</h2>
                            <p className="text-sm text-gray-600 mb-2">
                                Use this field to type notes and to store phrases selected from the description (by highlighting with your mouse).
                            </p>
                            <textarea
                                value={notes}
                                onChange={(e) => setNotes(e.target.value)}
                                rows="8"
                                placeholder="Enter notes here. E.g., 'Liked the remote-only option. Disliked the requirement for 8+ years experience.'"
                                className="w-full p-3 border border-gray-300 rounded-lg focus:ring-indigo-500 focus:border-indigo-500 shadow-sm"
                            ></textarea>
                        </div>

                        {/* Submission Button */}
                        <button
                            onClick={handleSubmit}
                            disabled={!job || submissionStatus === "Submitting..."}
                            className="w-full bg-indigo-600 text-white font-bold py-3 rounded-lg shadow-lg hover:bg-indigo-700 transition duration-150 disabled:bg-indigo-400"
                        >
                            {submissionStatus || `Submit Rating of ${overallScore}/10`}
                        </button>

                        {submissionStatus && submissionStatus.includes("saved") && (
                            <p className="text-center text-green-600 font-medium">{submissionStatus}</p>
                        )}

                        {submissionStatus && submissionStatus.includes("Error") && (
                            <p className="text-center text-red-600 font-medium">{submissionStatus}</p>
                        )}

                    </div>
                </div>

            </div>
        </div>
    );
}
