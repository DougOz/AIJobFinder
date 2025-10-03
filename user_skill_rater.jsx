import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { initializeApp } from 'firebase/app';
import {
    getAuth, signInAnonymously, signInWithCustomToken,
    onAuthStateChanged
} from 'firebase/auth';
import {
    getFirestore, doc, setDoc, collection, query,
    onSnapshot, serverTimestamp
} from 'firebase/firestore';

// --- Global Setup (Mandatory for Canvas Environment) ---
const firebaseConfig = typeof __firebase_config !== 'undefined' ? JSON.parse(__firebase_config) : {};
const initialAuthToken = typeof __initial_auth_token !== 'undefined' ? __initial_auth_token : null;
const appId = typeof __app_id !== 'undefined' ? __app_id : 'local-skill-rater-id'; // Updated default to match Python script

// Firestore Path Constants
const ROOT_COLLECTION = 'artifacts';
const PUBLIC_COLLECTION = 'public';
const USER_COLLECTION = 'users';

// Full paths for specific data points
const MASTER_SKILL_DOC_PATH = `${ROOT_COLLECTION}/${appId}/${PUBLIC_COLLECTION}/all_skills`;
const USER_SKILL_PROFILE_PATH = (userId) => `${ROOT_COLLECTION}/${appId}/${USER_COLLECTION}/${userId}/skill_ratings/user_profile`;
const USER_JOB_TRAINING_COLLECTION_PATH = (userId) => `${ROOT_COLLECTION}/${appId}/${USER_COLLECTION}/${userId}/job_training_data`;


// Initialize Firebase services outside the component to avoid re-initialization
let app, db, auth;
try {
    if (Object.keys(firebaseConfig).length > 0) {
        app = initializeApp(firebaseConfig);
        db = getFirestore(app);
        auth = getAuth(app);
    }
} catch (error) {
    console.error("Firebase initialization failed:", error);
}

// --- Skill Level Constants ---
const SKILL_LEVELS = {
    'STRONG': { label: 'Strong', color: 'bg-green-100 text-green-800 border-green-400 hover:bg-green-200' },
    'INTERMEDIATE': { label: 'Intermediate', color: 'bg-yellow-100 text-yellow-800 border-yellow-400 hover:bg-yellow-200' },
    'MINIMAL': { label: 'Minimal/None', color: 'bg-red-100 text-red-800 border-red-400 hover:bg-red-200' },
    'UNRATED': { label: 'Unrated', color: 'bg-gray-100 text-gray-600 border-gray-300 hover:bg-gray-200' },
};


// --- Mock Job Data (Preserved for Job Trainer section demo) ---
const MOCK_JOBS = [
    {
        id: 'job_001', title: "Senior Python Backend Engineer", skills: ["Python", "Django", "PostgreSQL", "AWS"],
        description: "We are seeking a highly skilled Senior Python Backend Engineer to lead our API development team. This role requires deep expertise in scalable cloud architecture, particularly using AWS services like S3 and EC2. You will be responsible for designing and implementing robust, high-performance APIs. Experience with real-time data processing and asynchronous tasks is a major plus. The ideal candidate thrives in a collaborative, fast-paced environment and is passionate about code quality and mentorship. Experience with Go or Rust is beneficial."
    },
    {
        id: 'job_002', title: "Frontend Developer (React/TS)", skills: ["React", "TypeScript", "Tailwind CSS", "Redux"],
        description: "Join our team to build the next generation of user interfaces. We focus on modern React with TypeScript and heavy use of Tailwind for aesthetic, responsive design. You must have a strong portfolio demonstrating expertise in component state management and performance optimization. This role is highly collaborative, working closely with UX/UI designers. Database knowledge is not essential, but a basic understanding of RESTful services is required."
    },
    {
        id: 'job_003', title: "Java Enterprise Architect", skills: ["Java", "Spring Boot", "JPA", "Microservices"],
        description: "A large enterprise is looking for an Architect to modernize their legacy systems using Java and Spring Boot. This involves designing microservice architectures and handling massive transaction loads. Familiarity with Kafka and containerization (Docker/Kubernetes) is mandatory. Strong communication skills are required for stakeholder management."
    },
];

// --- API Helper Function (Simulates Initial Matching Model) ---
const calculateSimilarityScore = async (resumeText, jobTitle, jobDescription) => {
    // [Implementation remains the same as previous file]
    if (!resumeText || !jobDescription) return { score: 0, summary: "Missing resume or description." };

    const systemPrompt = `You are a job matching expert. Compare the provided RESUME against the JOB POSTING. Provide a FIT_SCORE on a scale of 1 to 100 based on technical and experience overlap. Also, extract three key LIKED phrases (skills/experience matches) and three DISLIKED phrases (major skill gaps or mismatched requirements) from the job description based on the resume.`;
    const userQuery = `RESUME:\n---\n${resumeText}\n---\n\nJOB POSTING TITLE: ${jobTitle}\nJOB POSTING DESCRIPTION:\n---\n${jobDescription}`;

    // Define the structured JSON output schema
    const payload = {
        contents: [{ parts: [{ text: userQuery }] }],
        systemInstruction: { parts: [{ text: systemPrompt }] },
        generationConfig: {
            responseMimeType: "application/json",
            responseSchema: {
                type: "OBJECT",
                properties: {
                    FIT_SCORE: { type: "NUMBER", description: "The calculated fit score (1-100)." },
                    JUSTIFICATION: { type: "STRING", description: "A brief reason for the score." },
                    LIKED_PHRASES: { type: "ARRAY", items: { type: "STRING" }, description: "3 phrases from the description that match the resume." },
                    DISLIKED_PHRASES: { type: "ARRAY", items: { type: "STRING" }, description: "3 phrases from the description that represent a gap or mismatch." }
                },
                required: ["FIT_SCORE", "JUSTIFICATION", "LIKED_PHRASES", "DISLIKED_PHRASES"]
            }
        }
    };

    const apiKey = ""; // Canvas environment provides this at runtime
    const apiUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key=${apiKey}`;

    try {
        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();
        const jsonText = result?.candidates?.[0]?.content?.parts?.[0]?.text;

        if (jsonText) {
            const parsedJson = JSON.parse(jsonText);
            return {
                score: parsedJson.FIT_SCORE || 0,
                summary: parsedJson.JUSTIFICATION || "Analysis complete.",
                liked_phrases: parsedJson.LIKED_PHRASES || [],
                disliked_phrases: parsedJson.DISLIKED_PHRASES || []
            };
        }
        console.error("Gemini response was empty or malformed:", result);
        return { score: 0, summary: "Error processing model output." };

    } catch (e) {
        console.error("Gemini API call failed:", e);
        // Implement exponential backoff here in a production environment
        return { score: 0, summary: `API Error: ${e.message}` };
    }
};


// --- React Component ---

const App = () => {
    // --- State Management ---
    const [userId, setUserId] = useState(null);
    const [isAuthReady, setIsAuthReady] = useState(false);
    const [viewMode, setViewMode] = useState('rater'); // 'rater' or 'trainer'

    // --- SKILL RATER STATES (NEW) ---
    const [masterSkills, setMasterSkills] = useState([]); // List of 5214 skills from public path
    const [ratedSkills, setRatedSkills] = useState({}); // { skillName: 'STRONG', skillName2: 'MINIMAL' }
    const [isSaving, setIsSaving] = useState(false);

    // --- JOB TRAINER STATES (EXISTING) ---
    const [resumeText, setResumeText] = useState("");
    const [jobs, setJobs] = useState([]);
    const [jobIndex, setJobIndex] = useState(0);
    const [filterPercent, setFilterPercent] = useState(25);
    const [currentScore, setCurrentScore] = useState(5); // 1-10 user score
    const [currentNotes, setCurrentNotes] = useState("");
    const [currentLikedPhrases, setCurrentLikedPhrases] = useState([]);
    const [currentDislikedPhrases, setCurrentDislikedPhrases] = useState([]);
    const [modelScore, setModelScore] = useState(0);
    const [modelSummary, setModelSummary] = useState("Awaiting resume input...");
    const [isProcessing, setIsProcessing] = useState(false);


    // --- Firebase Auth & Setup ---
    useEffect(() => {
        if (!auth) return;

        const signIn = async () => {
            try {
                if (initialAuthToken) {
                    await signInWithCustomToken(auth, initialAuthToken);
                } else {
                    await signInAnonymously(auth);
                }
            } catch (error) {
                console.error("Authentication Error:", error);
            }
        };

        const unsubscribe = onAuthStateChanged(auth, (user) => {
            if (user) {
                setUserId(user.uid);
            } else {
                setUserId(crypto.randomUUID()); // Anonymous ID fallback
            }
            setIsAuthReady(true);
        });

        signIn();
        return () => unsubscribe();
    }, []);

    // --- FIRESTORE LISTENERS (NEW) ---

    // 1. Fetch Master Skill List (Public Data)
    useEffect(() => {
        if (!db || !isAuthReady) return;

        const skillDocRef = doc(db, MASTER_SKILL_DOC_PATH);

        const unsubscribe = onSnapshot(skillDocRef, (docSnap) => {
            if (docSnap.exists() && docSnap.data().list) {
                console.log(`Fetched ${docSnap.data().list.length} skills from Firestore.`);
                setMasterSkills(docSnap.data().list);
            } else {
                console.warn("Master skill list document not found. Using empty list.");
                setMasterSkills([]);
            }
        }, (error) => console.error("Error fetching master skills list:", error));

        return () => unsubscribe();
    }, [db, isAuthReady]);

    // 2. Fetch User's Skill Ratings (Private Data)
    useEffect(() => {
        if (!db || !isAuthReady || !userId) return;

        const userProfileDocRef = doc(db, USER_SKILL_PROFILE_PATH(userId));

        const unsubscribe = onSnapshot(userProfileDocRef, (docSnap) => {
            if (docSnap.exists() && docSnap.data().ratings) {
                console.log("Loaded user skill ratings profile.");
                setRatedSkills(docSnap.data().ratings);
            } else {
                console.log("User skill ratings profile not found. Starting fresh.");
                setRatedSkills({});
            }
        }, (error) => console.error("Error fetching user skill ratings:", error));

        return () => unsubscribe();
    }, [db, isAuthReady, userId]);

    // --- Data Fetching (Simulated Jobs and Real Training Data) ---
    const currentJob = useMemo(() => jobs[jobIndex] || null, [jobs, jobIndex]);
    const jobCollectionPath = USER_JOB_TRAINING_COLLECTION_PATH(userId);

    // 3. Load mock jobs initially (Existing Logic)
    useEffect(() => {
        const jobsWithMockScores = MOCK_JOBS.map(job => ({
            ...job,
            model_score: job.id === 'job_001' ? 95 : (job.id === 'job_002' ? 65 : 30)
        }));
        setJobs(jobsWithMockScores);
    }, []);

    // 4. Real-time Listener for User's Job Training Data (Existing Logic)
    useEffect(() => {
        if (!db || !isAuthReady || !userId || !currentJob) return;

        const jobDocRef = doc(db, jobCollectionPath, currentJob.id);
        const unsubscribe = onSnapshot(jobDocRef, (docSnap) => {
            if (docSnap.exists()) {
                const data = docSnap.data();
                setCurrentScore(data.score || 5);
                setCurrentNotes(data.notes || "");
                setCurrentLikedPhrases(data.liked_phrases || []);
                setCurrentDislikedPhrases(data.disliked_phrases || []);
            } else {
                setCurrentScore(5);
                setCurrentNotes("");
                setCurrentLikedPhrases([]);
                setCurrentDislikedPhrases([]);
            }
            setModelScore(currentJob.model_score || 0);
            setModelSummary(currentJob.model_summary || "Initial score loaded.");

        }, (error) => console.error("Error fetching job training data:", error));

        return () => unsubscribe();
    }, [db, isAuthReady, userId, currentJob, jobCollectionPath]);


    // --- Core Logic ---

    // Saves the user's skill rating profile to Firestore (NEW)
    const saveUserRatings = useCallback(async () => {
        if (!db || !userId) {
            console.error("Cannot save: Database or user ID missing.");
            return;
        }

        setIsSaving(true);
        const docRef = doc(db, USER_SKILL_PROFILE_PATH(userId));
        const profileData = {
            userId: userId,
            ratings: ratedSkills,
            timestamp: serverTimestamp(),
        };

        try {
            await setDoc(docRef, profileData, { merge: true });
            console.log("User skill profile saved successfully.");
            alert("Skill profile saved successfully!"); // Use alert temporarily per previous instructions
        } catch (e) {
            console.error("Error saving user skill profile: ", e);
        } finally {
            setIsSaving(false);
        }
    }, [db, userId, ratedSkills]);

    // Updates a single skill rating in the local state (NEW)
    const handleSkillRate = useCallback((skill, level) => {
        setRatedSkills(prev => ({
            ...prev,
            [skill]: level,
        }));
    }, []);

    // Existing job trainer functions (omitted for brevity, assume they remain the same)
    // ... [filteredJobs, handleInitialMatchFilter, saveTrainingData, handleNextJob, handlePhraseToggle] ...

    const filteredJobs = useMemo(() => {
        if (!jobs.length) return [];

        const scoredJobs = jobs.filter(j => j.model_score !== undefined);
        scoredJobs.sort((a, b) => b.model_score - a.model_score);

        const cutoffIndex = Math.ceil(scoredJobs.length * (filterPercent / 100));

        return scoredJobs.slice(0, cutoffIndex);
    }, [jobs, filterPercent]);

    useEffect(() => {
        if (jobIndex >= filteredJobs.length && filteredJobs.length > 0) {
            setJobIndex(0);
        } else if (filteredJobs.length === 0) {
            setJobIndex(0);
        }
    }, [filteredJobs, jobIndex]);

    const handleInitialMatchFilter = useCallback(async () => {
        if (!resumeText || jobs.length === 0) return alert("Please enter your resume text first.");
        if (isProcessing) return;

        setIsProcessing(true);
        const newJobs = await Promise.all(jobs.map(async (job) => {
            const { score, summary, liked_phrases, disliked_phrases } = await calculateSimilarityScore(
                resumeText, job.title, job.description
            );

            if (job.id === currentJob.id) {
                setCurrentLikedPhrases(liked_phrases);
                setCurrentDislikedPhrases(disliked_phrases);
            }

            return {
                ...job,
                model_score: score,
                model_summary: summary,
                predicted_liked: liked_phrases,
                predicted_disliked: disliked_phrases
            };
        }));

        setJobs(newJobs);
        setIsProcessing(false);
        setJobIndex(0);
    }, [resumeText, jobs, currentJob]);


    const saveTrainingData = useCallback(async () => {
        if (!db || !userId || !currentJob) {
            console.error("Cannot save: Database, user ID, or current job missing.");
            return;
        }

        const docRef = doc(db, jobCollectionPath, currentJob.id);
        const trainingData = {
            jobId: currentJob.id,
            score: currentScore,
            notes: currentNotes,
            liked_phrases: currentLikedPhrases,
            disliked_phrases: currentDislikedPhrases,
            timestamp: serverTimestamp(),
            initial_model_score: modelScore,
            initial_model_summary: modelSummary
        };

        try {
            await setDoc(docRef, trainingData, { merge: true });
            console.log("Training data saved for job:", currentJob.id);
        } catch (e) {
            console.error("Error adding document: ", e);
        }
    }, [db, userId, currentJob, currentScore, currentNotes, currentLikedPhrases, currentDislikedPhrases, modelScore, modelSummary, jobCollectionPath]);

    const handleNextJob = useCallback(async () => {
        if (!currentJob) return;

        await saveTrainingData();

        if (jobIndex < filteredJobs.length - 1) {
            setJobIndex(prev => prev + 1);
        } else {
            setJobIndex(0);
            alert("End of the filtered list reached. Looping back to the first job.");
        }
    }, [jobIndex, filteredJobs.length, currentJob, saveTrainingData]);

    const handlePhraseToggle = (phrase, type) => {
        const setPhraseState = type === 'like' ? setCurrentLikedPhrases : setCurrentDislikedPhrases;
        const currentPhrases = type === 'like' ? currentLikedPhrases : currentDislikedPhrases;
        const otherPhrases = type === 'like' ? currentDislikedPhrases : currentLikedPhrases;
        const setOtherPhraseState = type === 'like' ? setCurrentDislikedPhrases : setCurrentLikedPhrases;

        if (currentPhrases.includes(phrase)) {
            setPhraseState(currentPhrases.filter(p => p !== phrase));
        } else {
            setPhraseState([...currentPhrases, phrase]);
            setOtherPhraseState(otherPhrases.filter(p => p !== phrase));
        }
    };


    // --- Utility Components (Existing Logic) ---

    const LoadingSpinner = () => (
        <div className="flex items-center space-x-2 text-indigo-500">
            <svg className="animate-spin h-5 w-5 mr-3" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Processing...
        </div>
    );

    const JobDescriptionAnnotator = ({ job, liked, disliked, onToggle }) => {
        if (!job) return null;

        const tokenize = (text) => text.split(/(\s+|[.,?!:;'"()])/).filter(t => t.trim() !== '');

        return (
            <div className="text-gray-700 leading-relaxed max-h-96 overflow-y-auto bg-gray-50 p-4 rounded-lg">
                <p className="text-sm font-semibold mb-2 text-indigo-600">Click words/phrases below to highlight them as liked/disliked training data.</p>
                {tokenize(job.description).map((token, index) => {
                    const isLiked = liked.includes(token);
                    const isDisliked = disliked.includes(token);

                    let classes = "cursor-pointer transition-all duration-150 rounded-sm";
                    if (isLiked) {
                        classes += " bg-emerald-200 text-emerald-800 font-medium shadow-md ring-2 ring-emerald-500";
                    } else if (isDisliked) {
                        classes += " bg-red-200 text-red-800 font-medium shadow-md ring-2 ring-red-500";
                    } else {
                        classes += " hover:bg-yellow-100";
                    }

                    if (token.match(/(\s+|[.,?!:;'"()])/)) {
                        return <span key={index}>{token}</span>;
                    }

                    return (
                        <span
                            key={index}
                            className={classes}
                            onClick={() => {
                                if (isLiked) {
                                    onToggle(token, 'dislike');
                                } else if (isDisliked) {
                                    onToggle(token, 'like');
                                } else {
                                    onToggle(token, 'like');
                                }
                            }}
                        >
                            {token}
                        </span>
                    );
                })}
            </div>
        );
    };

    // --- NEW SKILL RATER SECTION ---
    const SkillRaterSection = () => {
        const [searchTerm, setSearchTerm] = useState('');

        const filteredSkills = useMemo(() => {
            if (!masterSkills.length) return [];

            let skills = masterSkills.map(skill => ({
                name: skill,
                level: ratedSkills[skill] || 'UNRATED'
            }));

            // Filter by search term
            if (searchTerm) {
                skills = skills.filter(s => s.name.toLowerCase().includes(searchTerm.toLowerCase()));
            }

            // Always display unrated skills first, then Strong, then Intermediate, then Minimal
            const ratingOrder = ['UNRATED', 'STRONG', 'INTERMEDIATE', 'MINIMAL'];

            skills.sort((a, b) => {
                // Primary sort: Unrated first
                const ratingA = ratingOrder.indexOf(a.level);
                const ratingB = ratingOrder.indexOf(b.level);
                if (ratingA !== ratingB) {
                    return ratingA - ratingB;
                }
                // Secondary sort: Alphabetical
                return a.name.localeCompare(b.name);
            });

            return skills;
        }, [masterSkills, ratedSkills, searchTerm]);

        return (
            <div className="bg-white p-6 rounded-xl shadow-lg border border-indigo-100">
                <h2 className="text-2xl font-semibold text-indigo-600 mb-4">Skill Profile Rater ({filteredSkills.length} Displayed)</h2>

                <div className="flex flex-col md:flex-row gap-4 mb-4">
                    <input
                        type="text"
                        placeholder="Search for a skill (e.g., Python, AWS)"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="flex-grow border border-gray-300 rounded-lg p-3 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                    />
                    <button
                        onClick={saveUserRatings}
                        disabled={isSaving}
                        className="flex-shrink-0 inline-flex items-center justify-center px-6 py-2 border border-transparent text-base font-medium rounded-full shadow-sm text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition-colors disabled:bg-green-300"
                    >
                        {isSaving ? 'Saving...' : 'Save Skill Profile'}
                    </button>
                </div>

                <p className="text-sm text-gray-500 mb-4">
                    Total Skills Loaded: **{masterSkills.length}**. Rate your proficiency to power the weighted job matching algorithm.
                </p>

                <div className="max-h-[70vh] overflow-y-auto pr-2">
                    {masterSkills.length === 0 ? (
                        <div className="text-center py-10 text-gray-500">
                            {isAuthReady ? "Loading skills from Firestore..." : "Authenticating..."}
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {filteredSkills.map(skill => {
                                const currentLevel = SKILL_LEVELS[skill.level];

                                return (
                                    <div key={skill.name} className="flex flex-col sm:flex-row items-start sm:items-center justify-between p-3 border rounded-xl bg-white shadow-sm transition-shadow hover:shadow-md">
                                        <span className={`font-medium text-lg mb-2 sm:mb-0 ${skill.level === 'UNRATED' ? 'text-gray-900' : 'text-indigo-800'}`}>
                                            {skill.name}
                                        </span>
                                        <div className="flex flex-wrap gap-2">
                                            {Object.keys(SKILL_LEVELS).filter(k => k !== 'UNRATED').map(levelKey => {
                                                const level = SKILL_LEVELS[levelKey];
                                                const isActive = skill.level === levelKey;
                                                return (
                                                    <button
                                                        key={levelKey}
                                                        onClick={() => handleSkillRate(skill.name, levelKey)}
                                                        className={`text-xs font-semibold px-3 py-1 rounded-full border transition-all duration-150 ${level.color} ${isActive ? 'shadow-inner scale-105' : 'opacity-70 hover:opacity-100'}`}
                                                    >
                                                        {level.label}
                                                    </button>
                                                );
                                            })}
                                            {skill.level !== 'UNRATED' && (
                                                <button
                                                    onClick={() => handleSkillRate(skill.name, 'UNRATED')}
                                                    className="text-xs font-semibold px-3 py-1 rounded-full border border-gray-400 bg-gray-50 text-gray-600 hover:bg-gray-200"
                                                >
                                                    Clear
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>
        );
    };


    // --- Main Render ---

    return (
        <div className="min-h-screen bg-gray-50 p-4 md:p-8 font-['Inter']">
            <script src="https://cdn.tailwindcss.com"></script>

            <div className="max-w-7xl mx-auto">
                <h1 className="text-4xl font-extrabold text-indigo-700 mb-2">Job Match Training Studio</h1>
                <p className="text-gray-500 mb-8 flex flex-wrap items-center gap-x-4">
                    Annotate and score jobs to train your personalized fit model.
                    <span className="text-sm text-gray-500">User ID: <span className="font-mono text-xs bg-gray-200 p-1 rounded">{userId || "Authenticating..."}</span></span>
                </p>

                {/* --- View Toggle --- */}
                <div className="flex mb-8 gap-2 border-b border-gray-200">
                    <button
                        onClick={() => setViewMode('rater')}
                        className={`py-2 px-4 text-lg font-medium rounded-t-lg transition-colors ${viewMode === 'rater' ? 'border-b-4 border-indigo-600 text-indigo-700' : 'text-gray-500 hover:text-indigo-500'}`}
                    >
                        1. Skill Rater
                    </button>
                    <button
                        onClick={() => setViewMode('trainer')}
                        className={`py-2 px-4 text-lg font-medium rounded-t-lg transition-colors ${viewMode === 'trainer' ? 'border-b-4 border-indigo-600 text-indigo-700' : 'text-gray-500 hover:text-indigo-500'}`}
                    >
                        2. Job Trainer
                    </button>
                </div>


                {/* --- RATER VIEW --- */}
                {viewMode === 'rater' && (
                    <SkillRaterSection />
                )}

                {/* --- TRAINER VIEW (Existing Logic) --- */}
                {viewMode === 'trainer' && (
                    <>
                        {/* --- 1. Resume Input & Filtering --- */}
                        <div className="bg-white p-6 rounded-xl shadow-lg mb-8 border border-indigo-100">
                            <h2 className="text-2xl font-semibold text-indigo-600 mb-4">1. Model Initialization & Filtering</h2>

                            <div className="grid md:grid-cols-3 gap-6">
                                <div className="md:col-span-2">
                                    <label htmlFor="resume" className="block text-sm font-medium text-gray-700 mb-1">Paste Your Resume (Text Only)</label>
                                    <textarea
                                        id="resume"
                                        rows="4"
                                        className="w-full border border-gray-300 rounded-lg p-3 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                                        placeholder="Paste your relevant work experience, skills, and education here..."
                                        value={resumeText}
                                        onChange={(e) => setResumeText(e.target.value)}
                                    ></textarea>
                                    <button
                                        onClick={handleInitialMatchFilter}
                                        disabled={!resumeText || isProcessing}
                                        className="mt-3 w-full md:w-auto inline-flex items-center justify-center px-6 py-2 border border-transparent text-base font-medium rounded-full shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors disabled:bg-indigo-300"
                                    >
                                        {isProcessing ? <LoadingSpinner /> : "Run Initial Model Match"}
                                    </button>
                                </div>

                                <div className="md:col-span-1 bg-indigo-50 p-4 rounded-xl">
                                    <h3 className="text-lg font-semibold text-indigo-800 mb-2">Filtering Settings</h3>
                                    <p className="text-sm text-indigo-700 mb-4">
                                        Jobs Loaded: **{jobs.length}** |
                                        Jobs Filtered (Top {filterPercent}%): **{filteredJobs.length}**
                                    </p>

                                    <label htmlFor="filter-percent" className="block text-sm font-medium text-indigo-700">
                                        Filter Jobs (Display Top {filterPercent}%)
                                    </label>
                                    <input
                                        id="filter-percent"
                                        type="range"
                                        min="10"
                                        max="100"
                                        step="5"
                                        value={filterPercent}
                                        onChange={(e) => setFilterPercent(parseInt(e.target.value))}
                                        className="w-full h-2 bg-indigo-200 rounded-lg appearance-none cursor-pointer range-lg mt-2"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* --- 2. Job Display & Annotation --- */}

                        {filteredJobs.length === 0 ? (
                            <div className="text-center py-20 bg-white rounded-xl shadow-lg border border-gray-200">
                                <p className="text-xl text-gray-500">
                                    {jobs.length > 0 ? "Adjust the filter or run the Initial Model Match to see jobs." : "No jobs loaded. Please check data source."}
                                </p>
                            </div>
                        ) : (
                            <div className="grid lg:grid-cols-3 gap-8">
                                {/* LEFT COLUMN: Job Card & Annotations */}
                                <div className="lg:col-span-2 space-y-6">
                                    <div className="bg-white p-6 rounded-xl shadow-xl border-t-4 border-indigo-600">
                                        <span className="text-sm font-semibold text-gray-500 block mb-2">Job {jobIndex + 1} of {filteredJobs.length} (Initial Model Fit: <span className={`font-bold ${modelScore >= 70 ? 'text-green-600' : modelScore >= 40 ? 'text-yellow-600' : 'text-red-600'}`}>{modelScore}%</span>)</span>
                                        <h2 className="text-3xl font-bold text-gray-900 mb-2">{currentJob?.title}</h2>
                                        <div className="flex flex-wrap gap-2 mb-4">
                                            {currentJob?.skills.map(skill => (
                                                <span key={skill} className="text-xs font-medium bg-indigo-100 text-indigo-800 px-3 py-1 rounded-full">{skill}</span>
                                            ))}
                                        </div>
                                        <p className="text-sm text-gray-600 italic mb-4 border-l-4 border-indigo-200 pl-3">{modelSummary}</p>

                                        {/* Job Description with Highlighting */}
                                        <h3 className="text-xl font-semibold text-gray-700 mb-3 mt-5">Job Description</h3>
                                        <JobDescriptionAnnotator
                                            job={currentJob}
                                            liked={currentLikedPhrases}
                                            disliked={currentDislikedPhrases}
                                            onToggle={handlePhraseToggle}
                                        />
                                    </div>

                                    {/* Annotation Summary */}
                                    <div className="bg-white p-6 rounded-xl shadow-md border border-gray-200">
                                        <h3 className="text-xl font-semibold text-gray-700 mb-3">Training Data Summary</h3>
                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="p-3 border rounded-lg bg-emerald-50">
                                                <p className="font-semibold text-emerald-700 mb-2">Phrases I Like (Matches)</p>
                                                <ul className="space-y-1 text-sm text-emerald-900">
                                                    {currentLikedPhrases.length > 0 ? currentLikedPhrases.map((p, i) => <li key={i}>&bull; {p}</li>) : <li className="italic text-gray-500">None selected.</li>}
                                                </ul>
                                            </div>
                                            <div className="p-3 border rounded-lg bg-red-50">
                                                <p className="font-semibold text-red-700 mb-2">Phrases I Dislike (Gaps)</p>
                                                <ul className="space-y-1 text-sm text-red-900">
                                                    {currentDislikedPhrases.length > 0 ? currentDislikedPhrases.map((p, i) => <li key={i}>&bull; {p}</li>) : <li className="italic text-gray-500">None selected.</li>}
                                                </ul>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* RIGHT COLUMN: Scoring & Controls */}
                                <div className="lg:col-span-1">
                                    <div className="sticky top-4 space-y-6">
                                        {/* User Score */}
                                        <div className="bg-white p-6 rounded-xl shadow-xl border border-indigo-200">
                                            <h3 className="text-2xl font-bold text-indigo-600 mb-4">2. Your Match Score (1-10)</h3>

                                            <div className="flex items-center justify-between mb-4">
                                                <span className="text-lg font-medium text-gray-700">Score:</span>
                                                <span className="text-4xl font-extrabold text-indigo-700">{currentScore}</span>
                                            </div>

                                            <input
                                                type="range"
                                                min="1"
                                                max="10"
                                                step="1"
                                                value={currentScore}
                                                onChange={(e) => setCurrentScore(parseInt(e.target.value))}
                                                className="w-full h-3 bg-indigo-200 rounded-lg appearance-none cursor-pointer range-xl"
                                            />
                                            <div className="flex justify-between text-xs text-gray-500 mt-1">
                                                <span>1 (Poor Match)</span>
                                                <span>10 (Perfect Match)</span>
                                            </div>
                                        </div>

                                        {/* Notes */}
                                        <div className="bg-white p-6 rounded-xl shadow-md border border-gray-200">
                                            <label htmlFor="notes" className="block text-lg font-semibold text-gray-700 mb-3">Notes / Rationale</label>
                                            <textarea
                                                id="notes"
                                                rows="4"
                                                className="w-full border border-gray-300 rounded-lg p-3 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                                                placeholder="E.g., 'Perfect technology stack, but location is a dealbreaker.' or 'Requires 5 years experience, I only have 3, so score is 6.'"
                                                value={currentNotes}
                                                onChange={(e) => setCurrentNotes(e.target.value)}
                                            ></textarea>
                                        </div>

                                        {/* Controls */}
                                        <div className="space-y-3">
                                            <button
                                                onClick={saveTrainingData}
                                                className="w-full flex items-center justify-center px-4 py-3 border border-transparent text-base font-medium rounded-xl shadow-sm text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition-colors"
                                            >
                                                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" viewBox="0 0 20 20" fill="currentColor">
                                                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4a1 1 0 000-1.414z" clipRule="evenodd" />
                                                </svg>
                                                Save Current Annotation
                                            </button>
                                            <button
                                                onClick={handleNextJob}
                                                className="w-full flex items-center justify-center px-4 py-3 border border-transparent text-base font-medium rounded-xl shadow-sm text-indigo-600 bg-indigo-100 hover:bg-indigo-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors"
                                            >
                                                Next Job (Save & Advance)
                                                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 ml-2" viewBox="0 0 20 20" fill="currentColor">
                                                    <path fillRule="evenodd" d="M10.293 15.707a1 1 0 010-1.414L12.586 12H7a1 1 0 010-2h5.586l-2.293-2.293a1 1 0 111.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                                                </svg>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
};

export default App;
