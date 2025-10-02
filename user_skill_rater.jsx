import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { initializeApp } from 'firebase/app';
import { getAuth, signInAnonymously, signInWithCustomToken, onAuthStateChanged } from 'firebase/auth';
import { getFirestore, doc, setDoc, onSnapshot } from 'firebase/firestore';

// --- Global Variables (Provided by Canvas Environment) ---
// Define these globally for the file, safely accessing the environment variables.
const appId = typeof __app_id !== 'undefined' ? __app_id : 'default-app-id';
const firebaseConfig = typeof __firebase_config !== 'undefined' ? JSON.parse(__firebase_config) : {};
const initialAuthToken = typeof __initial_auth_token !== 'undefined' ? __initial_auth_token : null;

// Mock master list of skills (will eventually be fetched from MongoDB)
const MOCK_MASTER_SKILLS = [
    "Python", "JavaScript", "React", "MongoDB", "SQL", "Tailwind CSS", "Data Analysis",
    "Machine Learning", "Cloud Computing", "AWS", "Docker", "Kubernetes", "Git", "Testing",
    "DevOps", "Node.js", "TypeScript", "C++", "Java", "Agile", "Scrum", "APIs", "Microservices"
];

// Rating Definitions
const RATING_DEFINITIONS = {
    3: { label: "Strong", color: "bg-green-500", shadow: "shadow-green-700", score: 3 },
    2: { label: "Intermediate", color: "bg-yellow-500", shadow: "shadow-yellow-700", score: 2 },
    1: { label: "Minimal/None", color: "bg-red-500", shadow: "shadow-red-700", score: 1 },
};

// --- Firestore/Auth Initialization ---
let db = null;
let auth = null;

const initializeFirebase = () => {
    try {
        const app = initializeApp(firebaseConfig);
        db = getFirestore(app);
        auth = getAuth(app);
        return { db, auth };
    } catch (error) {
        console.error("Firebase initialization failed:", error);
        return { db: null, auth: null };
    }
};

// --- Debounce Utility ---
const debounce = (func, delay) => {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), delay);
    };
};

// --- Rating Button Component ---
const RatingButton = React.memo(({ ratingValue, currentRating, onRate }) => {
    const definition = RATING_DEFINITIONS[ratingValue];
    const isActive = currentRating === ratingValue;

    return (
        <button
            onClick={() => onRate(ratingValue)}
            className={`
        w-full p-2 text-sm font-semibold rounded-lg transition duration-200
        ${isActive
                    ? `${definition.color} text-white shadow-md ${definition.shadow} scale-[1.02]`
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}
      `}
            aria-label={`Rate as ${definition.label}`}
        >
            {definition.label} ({definition.score})
        </button>
    );
});

// --- Skill Item Component ---
const SkillItem = React.memo(({ skill, currentRating, handleRate }) => {
    return (
        <div className="flex items-center justify-between p-4 bg-white rounded-xl shadow-sm border border-gray-200/50 hover:shadow-md transition duration-150">
            <span className="font-medium text-lg text-gray-800">{skill}</span>
            <div className="flex space-x-2 w-1/2 min-w-[200px]">
                {Object.values(RATING_DEFINITIONS).map((def) => (
                    <RatingButton
                        key={def.score}
                        ratingValue={def.score}
                        currentRating={currentRating}
                        onRate={(score) => handleRate(skill, score)}
                    />
                ))}
            </div>
        </div>
    );
});

// --- Main App Component ---
export default function App() {
    const [isAuthReady, setIsAuthReady] = useState(false);
    const [userId, setUserId] = useState(null);
    const [search, setSearch] = useState('');
    const [userRatings, setUserRatings] = useState({}); // { 'skillName': 3, ... }
    const [skills, setSkills] = useState(MOCK_MASTER_SKILLS.sort());
    const [saveStatus, setSaveStatus] = useState('Ready');

    // Firestore path for user ratings
    const getRatingsDocRef = useCallback((uid) => {
        if (!db || !uid) return null;
        return doc(db, `artifacts/${appId}/users/${uid}/skill_ratings/current_profile`);
    }, []);

    // Debounced function to write ratings to Firestore
    const saveRatingsToFirestore = useMemo(() => debounce(async (uid, ratings) => {
        if (!db || !uid) {
            console.error("Database not ready for saving.");
            setSaveStatus('Error: Database not ready');
            return;
        }
        const docRef = getRatingsDocRef(uid);
        try {
            setSaveStatus('Saving...');
            await setDoc(docRef, { ratings, lastUpdated: new Date() }, { merge: true });
            setSaveStatus('Saved!');
        } catch (e) {
            console.error("Error writing document: ", e);
            setSaveStatus('Error saving!');
        }
    }, 1000), [getRatingsDocRef]);

    // --- Initialization and Auth Effect ---
    useEffect(() => {
        const { db: initializedDb, auth: initializedAuth } = initializeFirebase();
        if (!initializedDb || !initializedAuth) return;

        const unsubscribe = onAuthStateChanged(initializedAuth, async (user) => {
            if (user) {
                setUserId(user.uid);
            } else {
                // Sign in anonymously if no custom token is available for full auth
                try {
                    if (initialAuthToken) {
                        const credential = await signInWithCustomToken(initializedAuth, initialAuthToken);
                        setUserId(credential.user.uid);
                    } else {
                        const credential = await signInAnonymously(initializedAuth);
                        setUserId(credential.user.uid);
                    }
                } catch (error) {
                    console.error("Firebase authentication failed:", error);
                }
            }
            setIsAuthReady(true);
        });

        return () => unsubscribe();
    }, []);

    // --- Firestore Listener Effect ---
    useEffect(() => {
        if (!isAuthReady || !userId) return;

        const docRef = getRatingsDocRef(userId);
        if (!docRef) return;

        // Set up real-time listener for user ratings
        const unsubscribe = onSnapshot(docRef, (doc) => {
            if (doc.exists()) {
                const data = doc.data();
                // Load skills from the 'ratings' map, ensuring unrated skills are represented as 0
                const loadedRatings = data.ratings || {};
                setUserRatings(loadedRatings);
            } else {
                // Doc doesn't exist, start with empty ratings
                setUserRatings({});
            }
        }, (error) => {
            console.error("Error listening to user ratings:", error);
        });

        // Cleanup the listener on unmount
        return () => unsubscribe();
    }, [isAuthReady, userId, getRatingsDocRef]);


    // --- Event Handlers ---
    const handleRate = useCallback((skill, score) => {
        setUserRatings(prevRatings => {
            const newRatings = { ...prevRatings, [skill]: score };
            // Immediately call the debounced save function
            saveRatingsToFirestore(userId, newRatings);
            return newRatings;
        });
    }, [userId, saveRatingsToFirestore]);


    // --- Filtered Skills List ---
    const filteredSkills = useMemo(() => {
        const lowerSearch = search.toLowerCase();
        return skills.filter(skill => skill.toLowerCase().includes(lowerSearch));
    }, [skills, search]);


    if (!isAuthReady) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-gray-50">
                <p className="text-xl text-indigo-600 font-semibold animate-pulse">Loading User Profile...</p>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 p-4 md:p-8 font-['Inter']">
            <header className="bg-white p-6 rounded-2xl shadow-lg mb-6">
                <h1 className="text-3xl font-extrabold text-indigo-700 mb-2">
                    Skill Profile Builder
                </h1>
                <p className="text-gray-600 mb-4">
                    Rate your proficiency on these job-derived skills. Scores are saved automatically.
                </p>
                <div className="flex flex-col sm:flex-row justify-between items-center space-y-2 sm:space-y-0">
                    <div className="flex items-center space-x-2 text-sm text-gray-500">
                        <svg className="w-5 h-5 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
                        <span>User ID: **{userId}**</span>
                    </div>
                    <div className="text-sm font-medium">
                        Status: <span className={saveStatus === 'Saved!' ? 'text-green-600' : saveStatus.startsWith('Error') ? 'text-red-600' : 'text-yellow-600'}>{saveStatus}</span>
                    </div>
                </div>
            </header>

            <section className="bg-white p-6 rounded-2xl shadow-lg mb-6">
                <h2 className="text-xl font-semibold text-gray-800 mb-4">Ratings Key</h2>
                <div className="flex flex-wrap gap-4">
                    {Object.values(RATING_DEFINITIONS).map(def => (
                        <div key={def.score} className="flex items-center space-x-2 p-3 bg-gray-50 rounded-lg border">
                            <span className={`w-3 h-3 rounded-full ${def.color.replace('bg-', 'bg-')}`}></span>
                            <span className="text-sm font-medium text-gray-700">{def.label} ({def.score})</span>
                        </div>
                    ))}
                    <div className="flex items-center space-x-2 p-3 bg-gray-50 rounded-lg border">
                        <span className={`w-3 h-3 rounded-full bg-gray-300`}></span>
                        <span className="text-sm font-medium text-gray-700">Unrated (0)</span>
                    </div>
                </div>
            </section>

            <section className="mb-8">
                <input
                    type="text"
                    placeholder="Search for a skill (e.g., Python, AWS)"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full p-4 border border-gray-300 rounded-xl shadow-inner focus:outline-none focus:ring-2 focus:ring-indigo-500 text-lg mb-6"
                />

                <div className="space-y-4">
                    {filteredSkills.length > 0 ? (
                        filteredSkills.map(skill => (
                            <SkillItem
                                key={skill}
                                skill={skill}
                                currentRating={userRatings[skill] || 0}
                                handleRate={handleRate}
                            />
                        ))
                    ) : (
                        <div className="text-center py-12 bg-white rounded-xl shadow-lg">
                            <p className="text-gray-500 text-xl">
                                {skills.length === 0 ? "No master skills loaded." : `No skills found matching "${search}".`}
                            </p>
                        </div>
                    )}
                </div>
            </section>
        </div>
    );
}
